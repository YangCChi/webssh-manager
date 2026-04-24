<template>
  <div
    class="terminal-pane"
    :style="{ display: visible ? 'flex' : 'none' }"
    ref="containerRef"
  >
    <!-- 顶部工具栏 -->
    <div class="terminal-toolbar">
      <span class="toolbar-host">
        <el-icon size="12"><Connection /></el-icon>
        <span v-if="serverInfo">{{ serverInfo.username }}@{{ serverInfo.host }}:{{ serverInfo.port }}</span>
        <span v-else-if="tabName" class="toolbar-host-placeholder">{{ tabName }}</span>
        <span v-else class="toolbar-host-placeholder">加载中...</span>
      </span>
      <span class="status-badge" :class="connStatus">
        <span class="status-dot" />
        {{ statusText }}
      </span>
      <div class="toolbar-spacer" />
      <div class="toolbar-actions">
        <el-tooltip content="SFTP文件管理" placement="bottom">
          <el-button text size="small" @click="$emit('open-sftp')">
            <el-icon><FolderOpened /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip content="搜索" placement="bottom">
          <el-button text size="small" @click="toggleSearch">
            <el-icon><Search /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip content="清屏" placement="bottom">
          <el-button text size="small" @click="clearTerminal">
            <el-icon><Delete /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip content="全屏" placement="bottom">
          <el-button text size="small" @click="toggleFullscreen">
            <el-icon><FullScreen /></el-icon>
          </el-button>
        </el-tooltip>
        <el-dropdown @command="setFontSize">
          <el-button text size="small">
            <el-icon><ZoomIn /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-for="s in [12, 13, 14, 15, 16, 18, 20]" :key="s" :command="s">
                {{ s }}px {{ fontSize === s ? '✓' : '' }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-dropdown @command="setTheme">
          <el-button text size="small">
            <el-icon><Brush /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="dark">暗黑 {{ currentTheme === 'dark' ? '✓' : '' }}</el-dropdown-item>
              <el-dropdown-item command="light">浅色 {{ currentTheme === 'light' ? '✓' : '' }}</el-dropdown-item>
              <el-dropdown-item command="monokai">Monokai {{ currentTheme === 'monokai' ? '✓' : '' }}</el-dropdown-item>
              <el-dropdown-item command="solarized">Solarized {{ currentTheme === 'solarized' ? '✓' : '' }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- 搜索栏 -->
    <div v-if="showSearch" class="search-bar">
      <el-input
        v-model="searchTerm"
        size="small"
        placeholder="搜索..."
        @input="doSearch"
        @keyup.enter="findNext"
        @keyup.escape="closeSearch"
        autofocus
      />
      <el-button size="small" @click="findNext">下一个</el-button>
      <el-button size="small" @click="findPrev">上一个</el-button>
      <el-button text size="small" @click="closeSearch"><el-icon><Close /></el-icon></el-button>
    </div>

    <!-- xterm 挂载点 -->
    <div class="xterm-mount" ref="xtermRef" />
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount, computed, nextTick } from 'vue'
import { Terminal } from 'xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import { SearchAddon } from '@xterm/addon-search'
import { toBase64 } from 'js-base64'
import {
  Connection, FolderOpened, Search, Delete, FullScreen, ZoomIn, Brush, Close,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import api from '@/utils/api'

const props = defineProps({
  sessionId: { type: String, required: true },
  visible: { type: Boolean, default: true },
  serverId: { type: Number, default: null },
  tabName: { type: String, default: '' },
})

const emit = defineEmits(['status-change', 'open-sftp'])

const authStore = useAuthStore()

const containerRef = ref(null)
const xtermRef = ref(null)
const connStatus = ref('connecting')
const serverInfo = ref(null)
const showSearch = ref(false)
const searchTerm = ref('')
const fontSize = ref(parseInt(localStorage.getItem('terminal_font_size') || '14'))
const currentTheme = ref(localStorage.getItem('terminal_theme') || 'dark')
const pendingInit = ref(false) // 等待 visible 才初始化

let term = null
let fitAddon = null
let searchAddon = null
let ws = null
let pingTimer = null
let resizeObserver = null
let resizeDebounceTimer = null  // 防抖：避免 resize 过于频繁

const statusText = computed(() => {
  const map = { connecting: '连接中...', active: '已连接', disconnected: '已断开', closed: '已关闭' }
  return map[connStatus.value] || connStatus.value
})

const THEMES = {
  dark: {
    background: '#0d1117', foreground: '#e6edf3', cursor: '#58a6ff',
    black: '#484f58', red: '#ff7b72', green: '#3fb950', yellow: '#d29922',
    blue: '#58a6ff', magenta: '#bc8cff', cyan: '#39c5cf', white: '#b1bac4',
    brightBlack: '#6e7681', brightRed: '#ffa198', brightGreen: '#56d364',
    brightYellow: '#e3b341', brightBlue: '#79c0ff', brightMagenta: '#d2a8ff',
    brightCyan: '#56d4dd', brightWhite: '#f0f6fc',
  },
  light: {
    background: '#ffffff', foreground: '#24292f', cursor: '#0969da',
    black: '#24292f', red: '#cf222e', green: '#1a7f37', yellow: '#9a6700',
    blue: '#0969da', magenta: '#8250df', cyan: '#1b7c83', white: '#6e7781',
    brightBlack: '#57606a', brightRed: '#a40e26', brightGreen: '#2da44e',
    brightYellow: '#bf8700', brightBlue: '#218bff', brightMagenta: '#a475f9',
    brightCyan: '#3192aa', brightWhite: '#8c959f',
  },
  monokai: {
    background: '#272822', foreground: '#f8f8f2', cursor: '#f8f8f0',
    black: '#272822', red: '#f92672', green: '#a6e22e', yellow: '#f4bf75',
    blue: '#66d9e8', magenta: '#ae81ff', cyan: '#a1efe4', white: '#f8f8f2',
    brightBlack: '#75715e', brightRed: '#f92672', brightGreen: '#a6e22e',
    brightYellow: '#f4bf75', brightBlue: '#66d9e8', brightMagenta: '#ae81ff',
    brightCyan: '#a1efe4', brightWhite: '#f9f8f5',
  },
  solarized: {
    background: '#002b36', foreground: '#839496', cursor: '#839496',
    black: '#073642', red: '#dc322f', green: '#859900', yellow: '#b58900',
    blue: '#268bd2', magenta: '#d33682', cyan: '#2aa198', white: '#eee8d5',
    brightBlack: '#002b36', brightRed: '#cb4b16', brightGreen: '#586e75',
    brightYellow: '#657b83', brightBlue: '#839496', brightMagenta: '#6c71c4',
    brightCyan: '#93a1a1', brightWhite: '#fdf6e3',
  },
}

function initTerminal() {
  if (!xtermRef.value) return

  term = new Terminal({
    fontSize: fontSize.value,
    fontFamily: '"Cascadia Code", "JetBrains Mono", "Fira Code", Menlo, Monaco, "Courier New", monospace',
    theme: THEMES[currentTheme.value],
    cursorBlink: true,
    scrollback: 5000,
    allowTransparency: false,
    macOptionIsMeta: true,
    rightClickSelectsWord: true,
    allowProposedApi: true,  // 启用实验性 API，支持更完整的终端功能（TUI 程序需要）
    convertEol: false,       // 不转换换行符，TUI 程序需要精确控制
  })

  fitAddon = new FitAddon()
  searchAddon = new SearchAddon()

  term.loadAddon(fitAddon)
  term.loadAddon(searchAddon)
  term.loadAddon(new WebLinksAddon())

  term.open(xtermRef.value)
  fitAddon.fit()

  // 延迟一帧再连接 WebSocket，确保：
  // 1. fitAddon.fit() 的尺寸已正确计算（容器已完成渲染）
  // 2. xterm.js 内部渲染管线已就绪（可以正确接收 tmux 重绘数据）
  // 不延迟的话，tmux attach 的重绘数据可能在 xterm 渲染前到达，导致内容丢失
  setTimeout(() => {
    connectWS()
  }, 50)

  // 触屏板/鼠标滚轮处理：
  // 发送鼠标滚轮转义序列给远端，而不是滚动 xterm scrollback
  // 这样 tmux（mouse on）和 TUI 程序（vim/htop/hermes）都能正确响应滚动
  // 转义序列格式：\x1b[<M;y;xM（按下）\x1b[<m;y;xM（释放），button 64=上滚, 65=下滚
  let wheelTimer = null
  let wheelAccum = 0
  const WHEEL_THRESHOLD = 3  // 累积 3 行再发送，避免触屏板过度灵敏

  term.element.addEventListener('wheel', (e) => {
    e.preventDefault()

    // 两种模式：
    // 1. 应用鼠标模式（tmux mouse on / TUI 程序开启鼠标）：发送鼠标转义序列
    // 2. 普通 shell：累积到阈值后滚动 xterm scrollback
    const isAppCursor = term.buffer.active.type === 'alternate'
    const lineHeight = term._core._renderService.dimensions.cssCellHeight || 16

    if (isAppCursor || term._core._mouseService._activeProtocol) {
      // TUI 程序或鼠标模式激活时，发送鼠标滚轮转义序列
      const direction = e.deltaY > 0 ? 65 : 64  // 65=滚下, 64=滚上
      // 计算鼠标位置（相对于终端字符网格）
      const rect = term.element.getBoundingClientRect()
      const col = Math.floor((e.clientX - rect.left) / (term._core._renderService.dimensions.cssCellWidth || 8)) + 1
      const row = Math.floor((e.clientY - rect.top) / lineHeight) + 1
      // 鼠标按下+释放模拟一次点击滚动
      const seq = `\x1b[<${direction};${col};${row}M\x1b[<${direction - 32};${col};${row}m`
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'input', data: toBase64(seq) }))
      }
    } else {
      // 普通 shell 模式：累积滚动 scrollback
      const delta = Math.round(e.deltaY / lineHeight)
      wheelAccum += delta || (e.deltaY > 0 ? 1 : -1)
      clearTimeout(wheelTimer)
      wheelTimer = setTimeout(() => {
        if (Math.abs(wheelAccum) >= WHEEL_THRESHOLD) {
          term.scrollLines(Math.sign(wheelAccum) * Math.max(1, Math.abs(wheelAccum)))
        }
        wheelAccum = 0
      }, 30)
    }
  }, { passive: false })

  // 记录上一次的尺寸，避免向 SSH 发送无意义的 resize（TUI 程序如 hermes 收到 resize 会清屏重绘）
  let lastCols = term.cols
  let lastRows = term.rows

  // 键盘输入
  term.onData((data) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'input', data: toBase64(data) }))
    }
  })

  // 终端大小变化 —— 只在列/行数实际变化时才通知 SSH
  term.onResize(({ cols, rows }) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      if (cols !== lastCols || rows !== lastRows) {
        lastCols = cols
        lastRows = rows
        ws.send(JSON.stringify({ type: 'resize', cols, rows }))
      }
    }
  })
}

function connectWS() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${protocol}//${location.host}/ws/terminal/${props.sessionId}`
  
  ws = new WebSocket(url)
  ws.binaryType = 'arraybuffer'
  
  ws.onopen = () => {
    // 发送认证
    ws.send(JSON.stringify({ type: 'auth', token: authStore.token }))

    // 发送当前终端尺寸（确保 SSH PTY 大小同步）
    ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }))

    // 定期心跳
    pingTimer = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30000)
  }
  
  ws.onmessage = (event) => {
    if (event.data instanceof ArrayBuffer) {
      // 收到 SSH 数据 = 连接已成功
      if (connStatus.value !== 'active') {
        connStatus.value = 'active'
        emit('status-change', 'active')
      }
      // SSH 输出：写入终端
      const data = new Uint8Array(event.data)
      term.write(data)
    } else {
      // JSON 控制消息
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'status') {
          connStatus.value = msg.status
          emit('status-change', msg.status)
        } else if (msg.type === 'pong') {
          // 心跳响应
        } else if (msg.type === 'error') {
          term.writeln(`\r\n\x1b[31m[错误] ${msg.message}\x1b[0m\r\n`)
        }
      } catch (e) {
        // 非JSON，尝试当作文本输出
        term.write(event.data)
      }
    }
  }
  
  ws.onclose = (event) => {
    clearInterval(pingTimer)
    // 只在非正常关闭时才标记为断开
    // 1000 = 正常关闭, 1001 = 终端离开
    if (event.code !== 1000 && event.code !== 1001) {
      connStatus.value = 'disconnected'
      emit('status-change', 'disconnected')
    }
  }
  
  ws.onerror = (err) => {
    console.error('WebSocket error:', err)
    // onerror 之后 onclose 一定会触发，不在 onerror 中设置状态
  }
}

// 监听容器大小变化自动 fit（加防抖，300ms 内只触发一次）
function startResizeObserver() {
  resizeObserver = new ResizeObserver(() => {
    if (!props.visible || !fitAddon) return
    clearTimeout(resizeDebounceTimer)
    resizeDebounceTimer = setTimeout(() => {
      fitAddon?.fit()
    }, 300)
  })
  if (containerRef.value) {
    resizeObserver.observe(containerRef.value)
  }
}

// visible 变化时触发 fit（切换标签）
watch(() => props.visible, async (v) => {
  if (v) {
    await nextTick()
    if (pendingInit.value) {
      // 首次变为可见，执行延迟初始化
      pendingInit.value = false
      initTerminal()
      startResizeObserver()
    } else {
      fitAddon?.fit()
      term?.focus()
    }
  }
})

function clearTerminal() {
  term?.clear()
}

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    containerRef.value?.requestFullscreen()
  } else {
    document.exitFullscreen()
  }
}

function setFontSize(size) {
  fontSize.value = size
  localStorage.setItem('terminal_font_size', size)
  term?.options.set('fontSize', size)
  fitAddon?.fit()
}

function setTheme(theme) {
  currentTheme.value = theme
  localStorage.setItem('terminal_theme', theme)
  if (term) term.options.theme = THEMES[theme]
}

function toggleSearch() {
  showSearch.value = !showSearch.value
  if (!showSearch.value) searchAddon?.clearDecorations()
}

function doSearch() {
  if (searchTerm.value) searchAddon?.findNext(searchTerm.value)
}

function findNext() { searchAddon?.findNext(searchTerm.value) }
function findPrev() { searchAddon?.findPrevious(searchTerm.value) }
function closeSearch() {
  showSearch.value = false
  searchAddon?.clearDecorations()
  term?.focus()
}

// 获取服务器信息（用于工具栏显示）
async function fetchServerInfo() {
  if (!props.serverId) return
  try {
    const res = await api.get(`/api/servers/${props.serverId}/connection-info`)
    serverInfo.value = res.data
  } catch (e) {
    // ignore
  }
}

onMounted(async () => {
  fetchServerInfo() // 不阻塞，后台加载工具栏信息
  // 等 DOM 渲染完且容器可见再初始化终端，避免 xterm 在隐藏容器里测量字宽出现 WWWWW
  await nextTick()
  // 若当前不可见，等到 visible 变为 true 时再初始化
  if (props.visible) {
    initTerminal()
    startResizeObserver()
  } else {
    // 标记待初始化，visible watcher 里会触发
    pendingInit.value = true
  }
})

onBeforeUnmount(() => {
  clearInterval(pingTimer)
  clearTimeout(resizeDebounceTimer)
  ws?.close()
  resizeObserver?.disconnect()
  term?.dispose()
})

// 暴露方法给父组件
defineExpose({ sendCommand: (cmd) => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'input', data: toBase64(cmd + '\n') }))
  }
}})
</script>

<style scoped>
.terminal-pane {
  flex-direction: column;
  height: 100%;
  width: 100%;
  position: absolute;
  inset: 0;
  background: var(--terminal-bg);
}

.terminal-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 12px;
  height: 36px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
  font-size: 12px;
}

.toolbar-host {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--text-secondary);
  white-space: nowrap;
  font-size: 12px;
}

.toolbar-host-placeholder {
  color: var(--text-secondary);
  opacity: 0.5;
}

.toolbar-spacer { flex: 1; }

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
}

.status-badge.active { background: rgba(63, 185, 80, 0.15); color: #3fb950; }
.status-badge.connecting { background: rgba(210, 153, 34, 0.15); color: #d29922; }
.status-badge.disconnected { background: rgba(248, 81, 73, 0.15); color: #f85149; }

.status-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }

.search-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.search-bar :deep(.el-input) { width: 200px; }

.xterm-mount {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding: 4px;
  position: relative;
}

.xterm-mount :deep(.xterm) {
  height: 100%;
  overflow: hidden;
}

.xterm-mount :deep(.xterm-screen) {
  height: 100%;
}

/* 隐藏 xterm 内部字宽测量元素 */
.xterm-mount :deep(.xterm-helpers) {
  position: absolute;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  width: 1px !important;
  height: 1px !important;
}
</style>
