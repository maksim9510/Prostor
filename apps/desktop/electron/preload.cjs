const { contextBridge, ipcRenderer, webUtils } = require('electron')

contextBridge.exposeInMainWorld('prostorDesktop', {
  getConnection: profile => ipcRenderer.invoke('prostor:connection', profile),
  revalidateConnection: () => ipcRenderer.invoke('prostor:connection:revalidate'),
  touchBackend: profile => ipcRenderer.invoke('prostor:backend:touch', profile),
  getGatewayWsUrl: profile => ipcRenderer.invoke('prostor:gateway:ws-url', profile),
  openSessionWindow: (sessionId, opts) => ipcRenderer.invoke('prostor:window:openSession', sessionId, opts),
  openNewSessionWindow: () => ipcRenderer.invoke('prostor:window:openNewSession'),
  getBootProgress: () => ipcRenderer.invoke('prostor:boot-progress:get'),
  getConnectionConfig: profile => ipcRenderer.invoke('prostor:connection-config:get', profile),
  saveConnectionConfig: payload => ipcRenderer.invoke('prostor:connection-config:save', payload),
  applyConnectionConfig: payload => ipcRenderer.invoke('prostor:connection-config:apply', payload),
  testConnectionConfig: payload => ipcRenderer.invoke('prostor:connection-config:test', payload),
  probeConnectionConfig: remoteUrl => ipcRenderer.invoke('prostor:connection-config:probe', remoteUrl),
  oauthLoginConnectionConfig: remoteUrl => ipcRenderer.invoke('prostor:connection-config:oauth-login', remoteUrl),
  oauthLogoutConnectionConfig: remoteUrl => ipcRenderer.invoke('prostor:connection-config:oauth-logout', remoteUrl),
  profile: {
    get: () => ipcRenderer.invoke('prostor:profile:get'),
    set: name => ipcRenderer.invoke('prostor:profile:set', name)
  },
  api: request => ipcRenderer.invoke('prostor:api', request),
  notify: payload => ipcRenderer.invoke('prostor:notify', payload),
  requestMicrophoneAccess: () => ipcRenderer.invoke('prostor:requestMicrophoneAccess'),
  readFileDataUrl: filePath => ipcRenderer.invoke('prostor:readFileDataUrl', filePath),
  readFileText: filePath => ipcRenderer.invoke('prostor:readFileText', filePath),
  selectPaths: options => ipcRenderer.invoke('prostor:selectPaths', options),
  writeClipboard: text => ipcRenderer.invoke('prostor:writeClipboard', text),
  saveImageFromUrl: url => ipcRenderer.invoke('prostor:saveImageFromUrl', url),
  saveImageBuffer: (data, ext) => ipcRenderer.invoke('prostor:saveImageBuffer', { data, ext }),
  saveClipboardImage: () => ipcRenderer.invoke('prostor:saveClipboardImage'),
  getPathForFile: file => {
    try {
      return webUtils.getPathForFile(file) || ''
    } catch {
      return ''
    }
  },
  normalizePreviewTarget: (target, baseDir) => ipcRenderer.invoke('prostor:normalizePreviewTarget', target, baseDir),
  watchPreviewFile: url => ipcRenderer.invoke('prostor:watchPreviewFile', url),
  stopPreviewFileWatch: id => ipcRenderer.invoke('prostor:stopPreviewFileWatch', id),
  setTitleBarTheme: payload => ipcRenderer.send('prostor:titlebar-theme', payload),
  setNativeTheme: mode => ipcRenderer.send('prostor:native-theme', mode),
  setTranslucency: payload => ipcRenderer.send('prostor:translucency', payload),
  setPreviewShortcutActive: active => ipcRenderer.send('prostor:previewShortcutActive', Boolean(active)),
  openExternal: url => ipcRenderer.invoke('prostor:openExternal', url),
  openPreviewInBrowser: url => ipcRenderer.invoke('prostor:openPreviewInBrowser', url),
  fetchLinkTitle: url => ipcRenderer.invoke('prostor:fetchLinkTitle', url),
  sanitizeWorkspaceCwd: cwd => ipcRenderer.invoke('prostor:workspace:sanitize', cwd),
  settings: {
    getDefaultProjectDir: () => ipcRenderer.invoke('prostor:setting:defaultProjectDir:get'),
    setDefaultProjectDir: dir => ipcRenderer.invoke('prostor:setting:defaultProjectDir:set', dir),
    pickDefaultProjectDir: () => ipcRenderer.invoke('prostor:setting:defaultProjectDir:pick')
  },
  revealLogs: () => ipcRenderer.invoke('prostor:logs:reveal'),
  getRecentLogs: () => ipcRenderer.invoke('prostor:logs:recent'),
  readDir: dirPath => ipcRenderer.invoke('prostor:fs:readDir', dirPath),
  gitRoot: startPath => ipcRenderer.invoke('prostor:fs:gitRoot', startPath),
  worktrees: cwds => ipcRenderer.invoke('prostor:fs:worktrees', cwds),
  terminal: {
    dispose: id => ipcRenderer.invoke('prostor:terminal:dispose', id),
    resize: (id, size) => ipcRenderer.invoke('prostor:terminal:resize', id, size),
    start: options => ipcRenderer.invoke('prostor:terminal:start', options),
    write: (id, data) => ipcRenderer.invoke('prostor:terminal:write', id, data),
    onData: (id, callback) => {
      const channel = `prostor:terminal:${id}:data`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)
      return () => ipcRenderer.removeListener(channel, listener)
    },
    onExit: (id, callback) => {
      const channel = `prostor:terminal:${id}:exit`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)
      return () => ipcRenderer.removeListener(channel, listener)
    }
  },
  onClosePreviewRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('prostor:close-preview-requested', listener)
    return () => ipcRenderer.removeListener('prostor:close-preview-requested', listener)
  },
  onOpenUpdatesRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('prostor:open-updates', listener)
    return () => ipcRenderer.removeListener('prostor:open-updates', listener)
  },
  onDeepLink: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('prostor:deep-link', listener)
    return () => ipcRenderer.removeListener('prostor:deep-link', listener)
  },
  signalDeepLinkReady: () => ipcRenderer.invoke('prostor:deep-link-ready'),
  onWindowStateChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('prostor:window-state-changed', listener)
    return () => ipcRenderer.removeListener('prostor:window-state-changed', listener)
  },
  onFocusSession: callback => {
    const listener = (_event, sessionId) => callback(sessionId)
    ipcRenderer.on('prostor:focus-session', listener)
    return () => ipcRenderer.removeListener('prostor:focus-session', listener)
  },
  onNotificationAction: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('prostor:notification-action', listener)
    return () => ipcRenderer.removeListener('prostor:notification-action', listener)
  },
  onPreviewFileChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('prostor:preview-file-changed', listener)
    return () => ipcRenderer.removeListener('prostor:preview-file-changed', listener)
  },
  onBackendExit: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('prostor:backend-exit', listener)
    return () => ipcRenderer.removeListener('prostor:backend-exit', listener)
  },
  onPowerResume: callback => {
    const listener = () => callback()
    ipcRenderer.on('prostor:power-resume', listener)
    return () => ipcRenderer.removeListener('prostor:power-resume', listener)
  },
  onBootProgress: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('prostor:boot-progress', listener)
    return () => ipcRenderer.removeListener('prostor:boot-progress', listener)
  },
  // First-launch bootstrap progress -- emitted by the install.ps1 stage
  // runner in main.cjs (apps/desktop/electron/bootstrap-runner.cjs).
  // Renderer's install overlay subscribes to live events and queries the
  // current snapshot via getBootstrapState() to recover after a devtools
  // reload mid-bootstrap.
  getBootstrapState: () => ipcRenderer.invoke('prostor:bootstrap:get'),
  resetBootstrap: () => ipcRenderer.invoke('prostor:bootstrap:reset'),
  repairBootstrap: () => ipcRenderer.invoke('prostor:bootstrap:repair'),
  cancelBootstrap: () => ipcRenderer.invoke('prostor:bootstrap:cancel'),
  onBootstrapEvent: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('prostor:bootstrap:event', listener)
    return () => ipcRenderer.removeListener('prostor:bootstrap:event', listener)
  },
  getVersion: () => ipcRenderer.invoke('prostor:version'),
  getRemoteDisplayReason: () => ipcRenderer.invoke('prostor:get-remote-display-reason'),
  uninstall: {
    summary: () => ipcRenderer.invoke('prostor:uninstall:summary'),
    run: mode => ipcRenderer.invoke('prostor:uninstall:run', { mode })
  },
  updates: {
    check: () => ipcRenderer.invoke('prostor:updates:check'),
    apply: opts => ipcRenderer.invoke('prostor:updates:apply', opts),
    getBranch: () => ipcRenderer.invoke('prostor:updates:branch:get'),
    setBranch: name => ipcRenderer.invoke('prostor:updates:branch:set', name),
    onProgress: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('prostor:updates:progress', listener)
      return () => ipcRenderer.removeListener('prostor:updates:progress', listener)
    }
  },
  themes: {
    fetchMarketplace: id => ipcRenderer.invoke('prostor:vscode-theme:fetch', id),
    searchMarketplace: query => ipcRenderer.invoke('prostor:vscode-theme:search', query)
  }
})
