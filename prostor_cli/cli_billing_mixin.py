"""Billing / credits / usage display methods for ``ProstorCLI``.

Extracted from ``cli.py`` as part of the god-file decomposition campaign
(Phase 4). This mixin holds the billing/credits/usage cluster: ``/usage``,
``/credits``, ``/billing`` (all 5 screens), charge polling, auto-reload, and
the monthly spend-limit screen.

Behavior-neutral: every method is lifted verbatim from ``ProstorCLI``.
``self.*`` calls resolve unchanged via the MRO. Neutral dependencies are
imported at module top level; ``cli.py``-internal helpers/constants are
imported lazily inside each method (``from cli import ...`` resolves at call
time, when ``cli`` is fully loaded) so this module never imports ``cli`` at
import time -> no import cycle.
"""

from __future__ import annotations

import concurrent.futures
import logging
from datetime import datetime

from prostor_cli.cli_skin import b as _b
from prostor_cli.cli_skin import d as _d
from prostor_cli.cli_utils import format_duration_compact


class CLIBillingMixin:
    """Mixin holding billing/credits/usage display methods for ``ProstorCLI``."""

    def _show_usage(self):
        """Rate limits + session token usage (when a live agent exists) + Nous credits.

        The Nous credits block is agent-independent (a portal fetch), so it runs even
        with no live agent — important for the TUI, where /usage runs in a slash-worker
        subprocess that resumes the session WITHOUT building an agent (self.agent is None),
        which would otherwise early-return before any credits showed.
        """
        from cli import CanonicalUsage, _cprint, estimate_usage_cost

        if not self.agent:
            if not self._print_nous_credits_block():
                print("(._.) No active agent -- send a message first.")
            return

        agent = self.agent
        calls = agent.session_api_calls

        if calls == 0:
            if not self._print_nous_credits_block():
                print("(._.) No API calls made yet in this session.")
            return

        # ── Rate limits (shown first when available) ────────────────
        rl_state = agent.get_rate_limit_state()
        if rl_state and rl_state.has_data:
            from agent.rate_limit_tracker import format_rate_limit_display
            print()
            print(format_rate_limit_display(rl_state))
            print()

        # ── Session token usage ─────────────────────────────────────
        input_tokens = getattr(agent, "session_input_tokens", 0) or 0
        output_tokens = getattr(agent, "session_output_tokens", 0) or 0
        cache_read_tokens = getattr(agent, "session_cache_read_tokens", 0) or 0
        cache_write_tokens = getattr(agent, "session_cache_write_tokens", 0) or 0
        reasoning_tokens = getattr(agent, "session_reasoning_tokens", 0) or 0
        prompt = agent.session_prompt_tokens
        completion = agent.session_completion_tokens
        total = agent.session_total_tokens

        compressor = agent.context_compressor
        last_prompt = compressor.last_prompt_tokens
        ctx_len = compressor.context_length
        pct = min(100, (last_prompt / ctx_len * 100)) if ctx_len else 0
        compressions = compressor.compression_count

        msg_count = len(self.conversation_history)
        cost_result = estimate_usage_cost(
            agent.model,
            CanonicalUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens,
                cache_write_tokens=cache_write_tokens,
            ),
            provider=getattr(agent, "provider", None),
            base_url=getattr(agent, "base_url", None),
        )
        elapsed = format_duration_compact((datetime.now() - self.session_start).total_seconds())

        print("  📊 Session Token Usage")
        print(f"  {'─' * 40}")
        print(f"  Model:                     {agent.model}")
        print(f"  Input tokens:              {input_tokens:>10,}")
        print(f"  Cache read tokens:         {cache_read_tokens:>10,}")
        print(f"  Cache write tokens:        {cache_write_tokens:>10,}")
        print(f"  Output tokens:             {output_tokens:>10,}")
        if reasoning_tokens:
            print(f"  ↳ Reasoning (subset):      {reasoning_tokens:>10,}")
        print(f"  Prompt tokens (total):     {prompt:>10,}")
        print(f"  Completion tokens:         {completion:>10,}")
        print(f"  Total tokens:              {total:>10,}")
        print(f"  API calls:                 {calls:>10,}")
        print(f"  Session duration:          {elapsed:>10}")
        print(f"  Cost status:              {cost_result.status:>10}")
        print(f"  Cost source:              {cost_result.source:>10}")
        if cost_result.amount_usd is not None:
            prefix = "~" if cost_result.status == "estimated" else ""
            print(f"  Total cost:              {prefix}${float(cost_result.amount_usd):>10.4f}")
        elif cost_result.status == "included":
            print(f"  Total cost:              {'included':>10}")
        else:
            print(f"  Total cost:              {'n/a':>10}")
        print(f"  {'─' * 40}")
        print(f"  Current context:  {last_prompt:,} / {ctx_len:,} ({pct:.0f}%)")
        print(f"  Messages:         {msg_count}")
        print(f"  Compressions:     {compressions}")
        if cost_result.status == "unknown":
            print(f"  Note:             Pricing unknown for {agent.model}")

        # Account limits -- fetched off-thread with a hard timeout so slow
        # provider APIs don't hang the prompt.
        provider = getattr(agent, "provider", None) or getattr(self, "provider", None)
        base_url = getattr(agent, "base_url", None) or getattr(self, "base_url", None)
        api_key = getattr(agent, "api_key", None) or getattr(self, "api_key", None)
        # Lazy import — pulls the OpenAI SDK chain, only needed here.
        from agent.account_usage import fetch_account_usage, render_account_usage_lines
        account_snapshot = None
        if provider:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
                try:
                    account_snapshot = _pool.submit(
                        fetch_account_usage, provider,
                        base_url=base_url, api_key=api_key,
                    ).result(timeout=10.0)
                except (concurrent.futures.TimeoutError, Exception):
                    account_snapshot = None
        account_lines = [f"  {line}" for line in render_account_usage_lines(account_snapshot)]
        if account_lines:
            print()
            for line in account_lines:
                print(line)

        # Nous credits magnitudes + monthly-grant gauge (agent-independent — also
        # runs at the no-agent / no-calls early-returns above). See the helper.
        self._print_nous_credits_block()

        if self.verbose:
            logging.getLogger().setLevel(logging.DEBUG)
            for noisy in ('openai', 'openai._base_client', 'httpx', 'httpcore', 'asyncio', 'hpack', 'grpc', 'modal'):
                logging.getLogger(noisy).setLevel(logging.WARNING)
        else:
            logging.getLogger().setLevel(logging.INFO)
            # NOTE: We deliberately do NOT raise per-logger levels for
            # tools/run_agent/etc. in quiet mode. Setting logger.setLevel
            # above the file handler level filters records before they
            # reach handlers, so agent.log / errors.log lose visibility
            # into stream-retry events, credential rotations, etc.
            # Console quietness is enforced by prostor_logging not
            # installing a console StreamHandler in non-verbose mode.

    def _print_nous_credits_block(self) -> bool:
        """Print the Nous credits magnitudes + monthly-grant gauge when a Nous account
        is logged in. Returns True if it printed anything.

        Delegates to the shared ``agent.account_usage.nous_credits_lines`` helper —
        the single source for the /usage credits block across CLI, gateway, and TUI.
        It's agent-independent (a portal fetch gated on "a Nous account is logged in",
        NOT the inference-provider string), so /usage shows the block even in the TUI
        slash-worker subprocess that resumes WITHOUT a live agent. Fail-open and
        wall-clock-bounded inside the helper; also honors PROSTOR_DEV_CREDITS_FIXTURE
        for offline testing — same behavior as every other surface.
        """
        from agent.account_usage import nous_credits_lines

        lines = nous_credits_lines()
        if not lines:
            return False
        print()
        for line in lines:
            print(f"  {line}")
        return True

    def _show_credits(self):
        """`/credits` — focused Nous credit balance + top-up handoff.

        Interactive CLI: balance block + identity line + a 3-button panel
        (Open top-up / Copy link / Cancel). Non-interactive contexts — the TUI
        slash-worker subprocess and any place without a live prompt_toolkit app
        (``self._app is None``) — render a text variant (balance + tappable
        top-up URL), because the modal would try to read the RPC stdin and crash
        the worker. The terminal never confirms or polls payment (billing phase
        2a). Fail-open: a portal hiccup or logged-out account degrades to a clear
        message, never a crash.
        """
        from cli import _cprint

        from agent.account_usage import build_credits_view

        view = build_credits_view()

        if not view.logged_in:
            print()
            _cprint(f"  💳 {_d('Not logged into Nous Portal.')}")
            print("  Run `prostor portal` to log in, then /credits.")
            return

        print()
        print("  💳 Nous credits")
        print(f"  {'─' * 41}")
        for line in view.balance_lines:
            # Drop the helper's own "📈 Nous credits" header — we print our own.
            if line.lstrip().startswith("📈"):
                continue
            print(f"  {line}")
        print(f"  {'─' * 41}")
        if view.identity_line:
            print(f"  {view.identity_line}")

        if not view.topup_url:
            return

        # Non-interactive (TUI slash-worker, piped, no live app): the
        # prompt_toolkit modal can't run here — it would read the worker's
        # JSON-RPC stdin and crash the command. Render the text variant: the
        # tappable URL IS the affordance, same as the messaging surfaces.
        if not getattr(self, "_app", None):
            print()
            print(f"  Top up: {view.topup_url}")
            print("  Complete your top-up in the browser — credits will appear in /credits shortly.")
            return

        choices = [
            ("open", "Open top-up in browser", "launch the portal billing page"),
            ("copy", "Copy link", "copy the top-up URL to your clipboard"),
            ("cancel", "Cancel", "do nothing"),
        ]
        raw = self._prompt_text_input_modal(
            title="💳 Add credits?",
            detail=f"Top-up page:\n{view.topup_url}",
            choices=choices,
        )
        choice = self._normalize_slash_confirm_choice(raw, choices)

        if choice == "open":
            opened = False
            try:
                import webbrowser

                opened = webbrowser.open(view.topup_url)
            except Exception:
                opened = False
            if not opened:
                print(f"  Open this URL to top up: {view.topup_url}")
            print()
            print("  Complete your top-up in the browser — credits will appear in /credits shortly.")
        elif choice == "copy":
            try:
                self._write_osc52_clipboard(view.topup_url)
                print(f"  📋 Copied: {view.topup_url}")
            except Exception:
                print(f"  Top-up URL: {view.topup_url}")
        else:
            print("  🟡 Cancelled. No credits added.")

    # ------------------------------------------------------------------
    # /billing — Phase 2b terminal billing (CLI surface, all 5 screens)
    # ------------------------------------------------------------------

    def _show_billing(self, command: str = "/billing"):
        """`/billing` — terminal billing for Nous (one interactive modal).

        ZERO sub-commands: any argument is ignored. Bare ``/billing`` always
        opens the Overview (Screen 1), whose numbered menu is the *only* way to
        reach the Buy / Auto-reload / Monthly-limit sub-screens. (Per the unified
        UX spec §0.4 — ``/billing buy`` etc. are gone; we don't error on a stray
        arg, we just open the menu.)

        Interactive CLI uses the prompt_toolkit modal; non-interactive contexts
        (TUI slash-worker / no live app) render text + the portal deep-link, never
        prompting (the URL is the affordance), same discipline as ``_show_credits``.
        All money is Decimal end-to-end; the terminal never collects card details.
        """
        from cli import _cprint

        from agent.billing_view import build_billing_state

        state = build_billing_state()
        if not state.logged_in:
            print()
            if state.error:
                _msg = f"Couldn't load billing: {state.error}"
                _cprint(f"  💳 {_d(_msg)}")
            else:
                _cprint(f"  💳 {_d('Not logged into Nous Portal.')}")
                print("  Run `prostor portal` to log in, then /billing.")
            return

        # Any sub-arg is intentionally ignored — always open the menu.
        self._billing_overview(state)

    def _billing_portal_hint(self, state, *, reason: str = "") -> None:
        """Print a portal deep-link line (the funnel for portal-only actions)."""
        url = getattr(state, "portal_url", None)
        if not url:
            return
        if reason:
            print(f"  {reason}")
        print(f"  Manage on portal: {url}")

    def _billing_overview(self, state):
        """Screen 1 — overview: balance, spend bar, role-gated action menu."""
        from cli import _cprint

        from agent.billing_view import format_money

        print()
        _cprint(f"  💳 {_b('Usage credits')}")
        print(f"  {'─' * 41}")

        cap = state.monthly_cap
        if cap is not None and cap.limit_usd is not None:
            spent = format_money(cap.spent_this_month_usd)
            limit = format_money(cap.limit_usd)
            ceiling = " (default ceiling)" if cap.is_default_ceiling else ""
            bar, pct = self._billing_spend_bar(
                cap.spent_this_month_usd, cap.limit_usd
            )
            print(f"  {spent} of {limit} used{ceiling}   {bar} {pct}%")

        print(f"  Balance: {format_money(state.balance_usd)}")

        ar = state.auto_reload
        if ar is not None:
            if ar.enabled:
                print(
                    f"  Auto-reload: on — below {format_money(ar.threshold_usd)} "
                    f"→ reload to {format_money(ar.reload_to_usd)}"
                )
            else:
                print("  Auto-reload: off")

        if state.org_name:
            role = (state.role or "").title()
            _org_line = f"Org: {state.org_name}{f' · {role}' if role else ''}"
            _cprint(f"  {_d(_org_line)}")
        print(f"  {'─' * 41}")

        # Action gating: admin + kill-switch for charge/auto-reload; everyone gets portal.
        if not state.is_admin:
            _cprint(f"  {_d('Billing actions require an org admin/owner.')}")
            self._billing_portal_hint(state)
            return
        if not state.cli_billing_enabled:
            _cprint(f"  {_d('Terminal billing is turned off for this org.')}")
            self._billing_portal_hint(state, reason="Enable it on the portal to buy credits here.")
            return

        # Optimistic funnel: no card on file → a charge will 403 no_payment_method.
        # Surface that up front (with the portal link) but DON'T hide Buy — /state.card
        # can't fully prove CLI-chargeability, so we advise rather than gate.
        if state.card is None:
            _cprint(
                f"  {_d('No saved card for terminal charges yet — set one up on the portal first.')}"
            )
            self._billing_portal_hint(state)

        # Non-interactive (slash-worker / no live app): no modal, no sub-command
        # advertising — just the portal funnel (the URL is the affordance).
        if not getattr(self, "_app", None):
            self._billing_portal_hint(state)
            return

        choices = [
            ("buy", "Buy credits", "purchase a one-time credit top-up"),
            ("auto", "Adjust auto-reload", "configure automatic top-ups"),
            ("limit", "Adjust monthly limit", "show the monthly spend cap (read-only)"),
            ("portal", "Manage on portal", "open the billing page in your browser"),
            ("cancel", "Cancel", "do nothing"),
        ]
        # The overview summary is already printed above; the modal only needs to
        # present the action menu — repeating the title/balance reads as a dupe.
        raw = self._prompt_text_input_modal(
            title="💳 Choose an action", detail="",
            choices=choices,
        )
        choice = self._normalize_slash_confirm_choice(raw, choices)
        if choice == "buy":
            self._billing_buy_flow(state)
        elif choice == "auto":
            self._billing_auto_reload_flow(state)
        elif choice == "limit":
            self._billing_limit_screen(state)
        elif choice == "portal":
            self._billing_open_portal(state)
        else:
            print("  🟡 Cancelled.")

    def _billing_spend_bar(self, spent, limit, *, cells: int = 10):
        """Render a 10-cell `█`/`░` spend bar + integer percent from spent/limit.

        Returns ``(bar, pct)`` where ``bar`` is like ``[████░░░░░░]`` and ``pct``
        is the spent/limit percentage clamped to 0..100. Box-drawing glyphs are
        not SGR codes, so this is leak-safe even without ``_b()``/``_d()``.
        """
        from decimal import Decimal

        try:
            s = Decimal(str(spent)) if spent is not None else Decimal("0")
            l = Decimal(str(limit)) if limit is not None else Decimal("0")
        except Exception:
            s, l = Decimal("0"), Decimal("0")
        if l <= 0:
            pct = 0
        else:
            pct = int((s / l) * 100)
        pct = max(0, min(100, pct))
        filled = int(round(pct / 100 * cells))
        filled = max(0, min(cells, filled))
        bar = ("█" * filled) + ("░" * (cells - filled))
        return bar, pct

    def _billing_open_portal(self, state):
        url = getattr(state, "portal_url", None)
        if not url:
            print("  No portal URL available.")
            return
        opened = False
        try:
            import webbrowser

            opened = webbrowser.open(url)
        except Exception:
            opened = False
        if not opened:
            print(f"  Open this URL: {url}")
        print("  Complete billing changes in the browser.")

    def _billing_require_admin(self, state) -> bool:
        """Guard charge/auto-reload entry points; print + return False if blocked."""
        from cli import _cprint

        if not state.is_admin:
            print()
            _cprint(f"  💳 {_d('Billing actions require an org admin/owner.')}")
            self._billing_portal_hint(state)
            return False
        if not state.cli_billing_enabled:
            print()
            _cprint(f"  💳 {_d('Terminal billing is turned off for this org.')}")
            self._billing_portal_hint(state, reason="Enable it on the portal first.")
            return False
        return True

    def _billing_buy_flow(self, state):
        """Screen 2 (preset select) → Screen 3 (confirm + charge + poll)."""
        from cli import _cprint

        from agent.billing_view import format_money, validate_charge_amount

        if not self._billing_require_admin(state):
            return

        # Screen 3 — preset selection.
        if not getattr(self, "_app", None):
            presets = ", ".join(format_money(p) for p in state.charge_presets)
            print()
            _cprint(f"  💳 {_b('Buy usage credits')}")
            print(f"  Presets: {presets}")
            print("  Run this in the interactive CLI to complete a purchase.")
            self._billing_portal_hint(state)
            return

        preset_choices = []
        for p in state.charge_presets:
            preset_choices.append((str(p), format_money(p), "one-time credit purchase"))
        preset_choices.append(("custom", "Custom amount…", "enter your own amount"))
        preset_choices.append(("cancel", "Cancel", "do nothing"))

        card = state.card
        detail = f"Payment: {card.masked}" if card else "No saved card on file"
        raw = self._prompt_text_input_modal(
            title="💳 Buy usage credits", detail=detail, choices=preset_choices,
        )
        choice = self._normalize_slash_confirm_choice(raw, preset_choices)
        if not choice or choice == "cancel":
            print("  🟡 Cancelled. No credits added.")
            return

        from decimal import Decimal

        if choice == "custom":
            entered = self._prompt_text_input("  Amount (USD): ")
            if entered is None:
                # None = cancelled (e.g. slash-worker can't prompt off-thread).
                print("  🟡 Cancelled. No credits added.")
                return
            v = validate_charge_amount(
                entered or "", min_usd=state.min_usd, max_usd=state.max_usd
            )
            if not v.ok:
                print(f"  🔴 {v.error}")
                return
            amount = v.amount
        else:
            try:
                amount = Decimal(choice)
            except Exception:
                print("  🔴 Invalid selection.")
                return

        self._billing_confirm_and_charge(state, amount)

    def _billing_confirm_and_charge(self, state, amount):
        """Screen 3 — confirm total + consent, charge, then poll to settlement."""
        from cli import _cprint

        from agent.billing_view import format_money, new_idempotency_key

        card = state.card
        print()
        _cprint(f"  💳 {_b('Confirm purchase')}")
        print(f"  {'─' * 41}")
        print(f"  Total: {format_money(amount)}")
        if card:
            print(f"  Payment: {card.masked}")
        print(f"  {'─' * 41}")
        _consent = (
            "By confirming, you allow Nous Research to charge your card."
        )
        _cprint(f"  {_d(_consent)}")

        confirm_choices = [
            ("pay", f"Pay {format_money(amount)} now", "submit the charge"),
            ("cancel", "Go back", "do not charge"),
        ]
        if not getattr(self, "_app", None):
            print("  Run in the interactive CLI to confirm a purchase.")
            return
        raw = self._prompt_text_input_modal(
            title=f"💳 Pay {format_money(amount)}?",
            detail=(card.masked if card else "no saved card"),
            choices=confirm_choices,
        )
        choice = self._normalize_slash_confirm_choice(raw, confirm_choices)
        if choice != "pay":
            print("  🟡 Cancelled. No credits added.")
            return

        # Submit the charge with a fresh idempotency key (reused on retry).
        from prostor_cli.nous_billing import (
            BillingError,
            BillingScopeRequired,
            post_charge,
        )

        key = new_idempotency_key()
        try:
            result = post_charge(amount_usd=amount, idempotency_key=key)
        except BillingScopeRequired:
            self._billing_handle_scope_required(state)
            return
        except BillingError as exc:
            self._billing_render_charge_error(state, exc)
            return

        charge_id = result.get("chargeId")
        if not charge_id:
            print("  🔴 No charge id returned; please check the portal.")
            return
        _cprint(f"  {_d('Charge submitted — confirming settlement…')}")
        self._billing_poll_charge(state, charge_id, amount)

    def _billing_poll_charge(self, state, charge_id, amount):
        """Poll loop: 2s interval, 5-min cap, cancellable. settled = ledger truth."""
        import time as _time

        from agent.billing_view import format_money
        from prostor_cli.nous_billing import (
            BillingError,
            BillingRateLimited,
            get_charge_status,
        )

        deadline = _time.time() + 300  # 5-minute cap
        interval = 2.0
        while _time.time() < deadline:
            try:
                status = get_charge_status(charge_id)
            except BillingRateLimited as exc:
                # Retry-after, NOT a failure — back off and keep polling.
                wait = exc.retry_after or 5
                _time.sleep(min(wait, 30))
                continue
            except BillingError as exc:
                print(f"  🔴 Could not check the charge: {exc}")
                return

            state_str = status.get("status")
            if state_str == "settled":
                amt = status.get("amountUsd")
                from agent.billing_view import parse_money

                shown = format_money(parse_money(amt)) if amt else format_money(amount)
                print(f"  ✅ {shown} in credits added.")
                return
            if state_str == "failed":
                self._billing_render_charge_failed(state, status.get("reason"))
                return
            # pending → wait and poll again
            _time.sleep(interval)

        # Past the cap with no terminal state = timeout (not an error).
        print("  🟡 Still processing after 5 minutes — this is a timeout, not a "
              "failure. Check /billing or the portal shortly.")
        self._billing_portal_hint(state)

    def _billing_render_charge_failed(self, state, reason):
        """Branch the poll `failed` reasons to the right copy + portal funnel."""
        reason = (reason or "").strip()
        if reason == "authentication_required":
            print("  🔴 Your bank requires verification (3DS). Complete it on the "
                  "portal to finish this purchase.")
        elif reason == "payment_method_expired":
            print("  🔴 Your card has expired. Update it on the portal.")
        elif reason == "card_declined":
            print("  🔴 Your card was declined. Try another card on the portal.")
        else:
            print(f"  🔴 The charge didn't go through ({reason or 'processing_error'}).")
        self._billing_portal_hint(state)

    def _billing_render_charge_error(self, state, exc):
        """Render a typed BillingError at submit time (pre-poll)."""
        from prostor_cli.nous_billing import BillingRateLimited

        code = getattr(exc, "error", None)
        portal_url = getattr(exc, "portal_url", None) or getattr(state, "portal_url", None)
        if code == "no_payment_method":
            print("  💳 No saved card for terminal charges yet. Set one up on the "
                  "portal (one-time credit buys don't save a reusable card).")
        elif code == "cli_billing_disabled":
            print("  🔴 Terminal billing is turned off for this org — an admin must enable it on the portal.")
        elif code == "monthly_cap_exceeded":
            remaining = (getattr(exc, "payload", {}) or {}).get("remainingUsd")
            if remaining is not None:
                print(f"  🔴 Monthly spend cap reached — ${remaining} headroom left.")
            else:
                print("  🔴 Monthly spend cap reached.")
        elif isinstance(exc, BillingRateLimited):
            wait = getattr(exc, "retry_after", None)
            mins = f" (try again in ~{max(1, round(wait / 60))} min)" if wait else ""
            print(f"  🟡 Too many charges right now{mins}. This isn't a payment failure.")
        else:
            print(f"  🔴 {exc}")
        if portal_url:
            print(f"  Portal: {portal_url}")

    def _billing_handle_scope_required(self, state):
        """403 insufficient_scope → lazy step-up re-auth (plan D-A)."""
        from cli import _cprint

        print()
        print("  💳 Terminal billing needs an extra permission (billing:manage).")
        _scope_msg = (
            "An org admin/owner must tick \"Allow terminal billing\" during "
            "login."
        )
        _cprint(f"  {_d(_scope_msg)}")
        if not getattr(self, "_app", None):
            print("  Run `prostor portal` and approve terminal billing, then retry.")
            return
        confirm_choices = [
            ("yes", "Re-authorize now", "open the portal to grant billing access"),
            ("no", "Not now", "cancel"),
        ]
        raw = self._prompt_text_input_modal(
            title="💳 Grant terminal billing access?",
            detail="Opens the portal device-authorization page.",
            choices=confirm_choices,
        )
        choice = self._normalize_slash_confirm_choice(raw, confirm_choices)
        if choice != "yes":
            print("  🟡 Cancelled.")
            return
        try:
            from prostor_cli.auth import step_up_nous_billing_scope

            granted = step_up_nous_billing_scope(open_browser=True)
        except Exception as exc:
            print(f"  🔴 Re-authorization failed: {exc}")
            return
        if granted:
            print("  ✅ Billing permission granted.")
            # Step-up only grants the billing:manage TOKEN scope; the ORG
            # kill-switch (cli_billing_enabled) is a separate gate. Re-fetch
            # /state so we don't over-promise when a charge would still hit
            # cli_billing_disabled.
            from agent.billing_view import build_billing_state

            fresh = build_billing_state()
            if fresh.logged_in and fresh.cli_billing_enabled:
                print("  Run /billing buy again to continue.")
            else:
                print("  🟡 Permission granted, but terminal billing is still turned "
                      "off for this org. Enable it in the portal, then run /billing again.")
                self._billing_portal_hint(fresh)
        else:
            print("  🟡 Terminal billing was not granted (an admin must tick the box).")

    def _billing_auto_reload_flow(self, state):
        """Screen 4 — auto-reload config: threshold + reload-to → PATCH.

        Prefills the current values from ``state.auto_reload``. Validates both
        amounts (2dp, within bounds, ``reload_to > threshold``). When auto-reload
        is already on, offers a "Turn off" path (PATCH ``enabled:false``).
        """
        from cli import _cprint

        from agent.billing_view import format_money, validate_charge_amount

        if not self._billing_require_admin(state):
            return

        card = state.card
        ar = state.auto_reload
        currently_on = bool(ar and ar.enabled)

        print()
        _cprint(f"  💳 {_b('Auto-reload')}")
        print(f"  {'─' * 41}")
        _cprint(f"  {_d('Automatically buy more credits when your balance is low.')}")
        if card:
            print(f"  Card on file: {card.masked}")
        else:
            print("  No saved card — set one up on the portal first.")
            self._billing_portal_hint(state)
            return
        if currently_on:
            print(
                f"  Currently: below {format_money(ar.threshold_usd)} → "
                f"reload to {format_money(ar.reload_to_usd)}"
            )

        if not getattr(self, "_app", None):
            print("  Run in the interactive CLI to configure auto-reload.")
            self._billing_portal_hint(state)
            return

        # When already enabled, let the user turn it off without re-entering values.
        if currently_on:
            top_choices = [
                ("edit", "Edit thresholds", "change when / how much to reload"),
                ("off", "Turn off", "disable auto-reload"),
                ("cancel", "Cancel", "do nothing"),
            ]
            raw = self._prompt_text_input_modal(
                title="💳 Auto-reload",
                detail=(
                    f"On — below {format_money(ar.threshold_usd)} → "
                    f"reload to {format_money(ar.reload_to_usd)}"
                ),
                choices=top_choices,
            )
            top = self._normalize_slash_confirm_choice(raw, top_choices)
            if top == "off":
                self._billing_auto_reload_disable(state)
                return
            if top != "edit":
                print("  🟡 Cancelled.")
                return

        # Field 1 — threshold (prefilled when editing an existing config).
        cur_thr = format_money(ar.threshold_usd) if currently_on else None
        thr_prompt = "  When balance falls below (USD)"
        thr_prompt += f" [{cur_thr}]: " if cur_thr else ": "
        threshold_raw = self._prompt_text_input(thr_prompt)
        if threshold_raw is None:
            # None = cancelled (e.g. slash-worker can't prompt off-thread).
            print("  🟡 Cancelled.")
            return
        if not (threshold_raw or "").strip() and currently_on:
            threshold_amt = ar.threshold_usd  # keep current value on empty input
        else:
            tv = validate_charge_amount(
                threshold_raw or "", min_usd=state.min_usd, max_usd=state.max_usd
            )
            if not tv.ok or tv.amount is None:
                print(f"  🔴 {tv.error}")
                return
            threshold_amt = tv.amount

        # Field 2 — reload-to (prefilled when editing an existing config).
        cur_rel = format_money(ar.reload_to_usd) if currently_on else None
        rel_prompt = "  Reload balance to (USD)"
        rel_prompt += f" [{cur_rel}]: " if cur_rel else ": "
        reload_raw = self._prompt_text_input(rel_prompt)
        if reload_raw is None:
            print("  🟡 Cancelled.")
            return
        if not (reload_raw or "").strip() and currently_on:
            reload_amt = ar.reload_to_usd  # keep current value on empty input
        else:
            rv = validate_charge_amount(
                reload_raw or "", min_usd=state.min_usd, max_usd=state.max_usd
            )
            if not rv.ok or rv.amount is None:
                print(f"  🔴 {rv.error}")
                return
            reload_amt = rv.amount

        if reload_amt is None or threshold_amt is None or reload_amt <= threshold_amt:
            print("  🔴 Reload-to amount must be greater than the threshold.")
            return

        print()
        _ar_consent = (
            f"By confirming, you authorize Nous Research to charge {card.masked} "
            f"whenever your balance reaches {format_money(threshold_amt)}. "
            f"Turn off any time here or on the portal."
        )
        _cprint(f"  {_d(_ar_consent)}")
        confirm_choices = [
            ("agree", "Agree and turn on", "enable auto-reload"),
            ("cancel", "Cancel", "do nothing"),
        ]
        raw = self._prompt_text_input_modal(
            title="💳 Turn on auto-reload?",
            detail=f"Below {format_money(threshold_amt)} → reload to {format_money(reload_amt)}",
            choices=confirm_choices,
        )
        choice = self._normalize_slash_confirm_choice(raw, confirm_choices)
        if choice != "agree":
            print("  🟡 Cancelled.")
            return

        from prostor_cli.nous_billing import (
            BillingError,
            BillingScopeRequired,
            patch_auto_top_up,
        )

        try:
            patch_auto_top_up(
                enabled=True, threshold=float(threshold_amt), top_up_amount=float(reload_amt)
            )
        except BillingScopeRequired:
            self._billing_handle_scope_required(state)
            return
        except BillingError as exc:
            self._billing_render_charge_error(state, exc)
            return
        print(f"  ✅ Auto-reload on: below {format_money(threshold_amt)} → "
              f"reload to {format_money(reload_amt)}.")

    def _billing_auto_reload_disable(self, state):
        """Turn off auto-reload (PATCH ``enabled:false``).

        The endpoint requires ``threshold``/``topUpAmount`` in the body even when
        disabling, so we echo back the current values (falling back to 0).
        """
        from prostor_cli.nous_billing import (
            BillingError,
            BillingScopeRequired,
            patch_auto_top_up,
        )

        ar = state.auto_reload
        thr = float(ar.threshold_usd) if ar and ar.threshold_usd is not None else 0.0
        rel = float(ar.reload_to_usd) if ar and ar.reload_to_usd is not None else 0.0
        try:
            patch_auto_top_up(enabled=False, threshold=thr, top_up_amount=rel)
        except BillingScopeRequired:
            self._billing_handle_scope_required(state)
            return
        except BillingError as exc:
            self._billing_render_charge_error(state, exc)
            return
        print("  ✅ Auto-reload turned off.")

    def _billing_limit_screen(self, state):
        """Screen 5 — monthly spend limit (read-only; cap is portal-only)."""
        from cli import _cprint

        from agent.billing_view import format_money

        print()
        _cprint(f"  💳 {_b('Monthly spend limit')}")
        print(f"  {'─' * 41}")
        cap = state.monthly_cap
        if cap is None or cap.limit_usd is None:
            _cprint(f"  {_d('No monthly cap visible (managed on the portal).')}")
        else:
            spent = format_money(cap.spent_this_month_usd)
            limit = format_money(cap.limit_usd)
            ceiling = " (default ceiling)" if cap.is_default_ceiling else ""
            print(f"  {spent} of {limit} used this month{ceiling}")
        _limit_note = (
            "The monthly limit is set on the portal — the terminal shows "
            "it read-only."
        )
        _cprint(f"  {_d(_limit_note)}")
        self._billing_portal_hint(state)