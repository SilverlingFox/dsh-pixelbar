import { spawn } from 'node:child_process'
import { existsSync, statSync } from 'node:fs'
import { dirname, isAbsolute, join } from 'node:path'
import { fileURLToPath } from 'node:url'

export const name = 'dsh-pixelbar'
export const inject = ['tools']

const HERE = dirname(fileURLToPath(import.meta.url))

const DEFAULTS = {
  // 留空 = 自动探测：环境变量 DSH_PIXELBAR_PYTHON → PATH 上的 python3 / python
  python: '',
  // 留空 = 用包内 scripts/ 下的脚本；相对路径相对于本文件所在目录
  script: join(HERE, 'scripts', 'halo_pixelbar.py'),
  clockScript: join(HERE, 'scripts', 'clock_restore.py'),
  defaultColor: 'magenta',
  restoreSeconds: 15,
}

const PYTHON_ENV = 'DSH_PIXELBAR_PYTHON'

const COLORS = ['white', 'red', 'green', 'blue', 'yellow', 'cyan', 'magenta']
const LAYOUTS = ['left', 'center', 'right', 'stretch', 'scroll_left_to_right', 'scroll_right_to_left']
const SCENES = ['clock', 'game', 'work', 'read', 'cats', 'dogs', 'memes', 'cyber', 'waves']
const EFFECTS = ['breathing', 'color_tide', 'static', 'ripple', 'flow', 'dynamic']
const LEVELS = ['low', 'medium', 'high']

// python.exe 是控制台程序，detached 启动时 Windows 会闪一下黑框；
// 换成 GUI 子系统的 pythonw.exe 就永远不会分配控制台窗口
function guiPython(python) {
  if (!/python\.exe$/i.test(String(python))) return python
  const w = String(python).replace(/python\.exe$/i, 'pythonw.exe')
  try {
    return existsSync(w) ? w : python
  } catch (e) {
    return python
  }
}

// 在 PATH 里找可执行文件，跳过 WindowsApps 那种 0 字节的商店 stub
function which(cmd) {
  const isWin = process.platform === 'win32'
  const exts = isWin
    ? String(process.env.PATHEXT || '.EXE;.COM;.BAT;.CMD').split(';').filter(Boolean)
    : ['']
  const names = /\.[a-z0-9]+$/i.test(cmd)
    ? [cmd]
    : exts.flatMap((e) => [cmd + e.toLowerCase(), cmd + e.toUpperCase()])
  const dirs = String(process.env.PATH || '').split(isWin ? ';' : ':').filter(Boolean)
  for (const dir of dirs) {
    for (const n of names) {
      const p = join(dir, n)
      try {
        if (existsSync(p) && statSync(p).size > 0) return p
      } catch (e) {
        // 无权限等，跳过
      }
    }
  }
  return null
}

function resolvePython(cfg) {
  const explicit = String(cfg.python || process.env[PYTHON_ENV] || '').trim()
  if (explicit) return guiPython(explicit)
  const found = which('python3') || which('python')
  return guiPython(found || 'python')
}

function resolveAsset(value, fallback) {
  const raw = String(value || '').trim()
  if (!raw) return fallback
  return isAbsolute(raw) ? raw : join(HERE, raw)
}

function runPy(python, args, timeoutMs) {
  return new Promise((resolve) => {
    let out = ''
    let err = ''
    let settled = false
    const done = (r) => { if (!settled) { settled = true; resolve(r) } }
    let child
    try {
      child = spawn(python, args, {
        windowsHide: true,
        env: Object.assign({}, process.env, { PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' }),
      })
    } catch (e) {
      return done({ ok: false, out: '', err: String((e && e.message) || e) })
    }
    const timer = setTimeout(() => {
      try { child.kill() } catch (e) { /* ignore */ }
      done({ ok: false, out: out.trim(), err: err.trim() || '超时 ' + timeoutMs + 'ms' })
    }, timeoutMs)
    child.stdout.on('data', (d) => { out += d.toString('utf8') })
    child.stderr.on('data', (d) => { err += d.toString('utf8') })
    child.on('error', (e) => { clearTimeout(timer); done({ ok: false, out: out.trim(), err: String((e && e.message) || e) }) })
    child.on('close', (code) => {
      clearTimeout(timer)
      done({ ok: code === 0, out: out.trim(), err: err.trim() })
    })
  })
}

function scheduleClockRestore(python, clockScript, seconds) {
  try {
    const child = spawn(python, [clockScript, String(seconds)], {
      detached: true,
      stdio: 'ignore',
      windowsHide: true,
      env: Object.assign({}, process.env, { PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' }),
    })
    child.unref()
    return true
  } catch (e) {
    return false
  }
}

function tail(text, n) {
  const t = String(text || '').trim()
  const limit = n || 300
  return t.length > limit ? '…' + t.slice(-limit) : t
}

export function apply(ctx, config) {
  const cfg = Object.assign({}, DEFAULTS, config || {})
  const python = resolvePython(cfg)
  const script = resolveAsset(cfg.script, DEFAULTS.script)
  const clockScript = resolveAsset(cfg.clockScript, DEFAULTS.clockScript)

  const tool = {
    name: 'pixelbar',
    description:
      '把短句推到桌面的 Halo PixelBar 像素屏（限 16 字符 / 48 字节，不要用 emoji，可用 ^_^ QAQ (T_T) 之类颜文字）；' +
      '推完默认 15 秒自动切回时钟。也能切场景、屏色、氛围灯、音量、查设备是否在线。',
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        action: {
          type: 'string',
          enum: ['text', 'scene', 'screen', 'light', 'volume', 'clock', 'status'],
          description: '默认 text。text=推文字；scene=切场景；screen=设屏色；light=氛围灯；volume=音量；clock=立刻回时钟；status=查设备',
        },
        text: { type: 'string', description: 'action=text 时要显示的文字（超过 16 字符会被截断）' },
        color: { type: 'string', enum: COLORS, description: '文字颜色，默认 magenta' },
        layout: { type: 'string', enum: LAYOUTS, description: '可选：文字布局 left/center/right/stretch/滚动' },
        scene: { type: 'string', enum: SCENES, description: 'action=scene 时的场景名' },
        hex: { type: 'string', description: 'action=screen / light 时的颜色，如 #F0B4C8（屏色自动套校准表）' },
        effect: { type: 'string', enum: EFFECTS, description: 'action=light 的灯效，默认 breathing' },
        brightness: { type: 'string', enum: LEVELS, description: 'action=light 的亮度，默认 medium' },
        speed: { type: 'number', description: 'action=light 的速度 1-10，默认 5' },
        volume: { type: 'number', description: 'action=volume 的音量 0-16；不填=查询当前音量' },
        clock_restore: { type: 'number', description: '推完多少秒切回时钟，默认 15；0=不回时钟' },
      },
    },
    output: {
      schema: { type: 'string' },
      render(_args, value) { return [{ type: 'text', text: value }] },
    },
    timeoutMs: 25000,
    async execute(args) {
      const a = args || {}
      const action = String(a.action || (a.text ? 'text' : 'status'))

      if (!existsSync(script)) {
        return '找不到像素屏脚本：' + script + '（检查插件是否完整安装，或在 config.script 里指定路径）'
      }

      if (action === 'text') {
        const raw = String(a.text || '').replace(/\s+/g, ' ').trim()
        if (!raw) return '（没有要推的文字）'
        const shown = Array.from(raw).slice(0, 16).join('')
        const color = COLORS.indexOf(a.color) >= 0 ? a.color : cfg.defaultColor
        const argv = [script, 'text', shown, '--color', color]
        if (LAYOUTS.indexOf(a.layout) >= 0) argv.push('--layout', a.layout)
        const r = await runPy(python, argv, 12000)
        if (!r.ok) return '推送失败：' + (tail(r.err) || tail(r.out) || '未知错误')
        const rest = Number(a.clock_restore)
        const seconds = Number.isFinite(rest) ? rest : (Number(cfg.restoreSeconds) || 15)
        const restored = seconds > 0 ? scheduleClockRestore(python, clockScript, seconds) : false
        const cut = raw !== shown ? '（已截到 16 字符）' : ''
        let note = ''
        if (seconds > 0) note = '；' + seconds + ' 秒后回时钟' + (restored ? '' : '（回时钟命令启动失败）')
        return '已推到像素屏：' + shown + cut + '；颜色 ' + color + note
      }

      if (action === 'scene') {
        if (SCENES.indexOf(a.scene) < 0) return 'scene 需为：' + SCENES.join('/')
        const r = await runPy(python, [script, 'ui', a.scene], 12000)
        return r.ok ? '已切场景：' + a.scene : '切场景失败：' + (tail(r.err) || tail(r.out))
      }

      if (action === 'screen') {
        const hex = String(a.hex || '').trim()
        if (!/^#?[0-9a-fA-F]{6}$/.test(hex)) return 'hex 需形如 #F0B4C8'
        const r = await runPy(python, [script, 'color', hex], 12000)
        return r.ok ? '已设屏色：' + (tail(r.out, 120) || hex) : '设屏色失败：' + (tail(r.err) || tail(r.out))
      }

      if (action === 'light') {
        const h = String(a.hex || '').trim()
        const hex = /^#?[0-9a-fA-F]{6}$/.test(h) ? h : '#F0B4C8'
        const argv = [script, 'light',
          '--effect', EFFECTS.indexOf(a.effect) >= 0 ? a.effect : 'breathing',
          '--color', hex,
          '--brightness', LEVELS.indexOf(a.brightness) >= 0 ? a.brightness : 'medium']
        const sp = Number(a.speed)
        if (Number.isFinite(sp)) argv.push('--speed', String(Math.max(1, Math.min(10, Math.round(sp)))))
        const r = await runPy(python, argv, 12000)
        return r.ok ? '氛围灯已设：' + tail(r.out, 120) : '氛围灯失败：' + (tail(r.err) || tail(r.out))
      }

      if (action === 'volume') {
        const has = a.volume !== undefined && a.volume !== null && a.volume !== ''
        const argv = has
          ? [script, 'volume', String(Math.max(0, Math.min(16, Math.round(Number(a.volume) || 0))))]
          : [script, 'volume']
        const r = await runPy(python, argv, 12000)
        return r.ok ? (tail(r.out, 120) || '已执行') : '音量操作失败：' + (tail(r.err) || tail(r.out))
      }

      if (action === 'clock') {
        const r = await runPy(python, [script, 'ui', 'clock'], 12000)
        return r.ok ? '已切回时钟' : '切时钟失败：' + (tail(r.err) || tail(r.out))
      }

      const r = await runPy(python, [script, 'list'], 12000)
      if (!r.ok) return '设备未找到：' + (tail(r.err) || tail(r.out))
      return '设备在线：' + tail(r.out, 200)
    },
  }

  const register = () => ctx.tools.register(tool)
  if (typeof ctx.effect === 'function') ctx.effect(register, 'dsh-pixelbar: pixelbar tool')
  else register()
}
