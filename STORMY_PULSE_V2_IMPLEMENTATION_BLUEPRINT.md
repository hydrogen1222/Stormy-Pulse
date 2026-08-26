# Stormy-Pulse V2：物理动力学音乐可视化重构实施蓝图

---

## 0. 给开发 Agent 的总指令

请不要把本文件理解成“再增加一些酷炫特效”的需求单。

Stormy-Pulse V2 的核心变化应该是：

```text
旧：
Audio Feature(t)
    ↓
Effect Parameter(t)
    ↓
Picture(t)

目标：
Audio Analysis
    ↓
Visual Context
    ↓
Evolving Artificial Material State
    ↓
Physical / Geometric Field
    ↓
Particles + Geometry + Color + Effects
    ↓
Picture(t)
```

换句话说：

> **音乐不直接控制特效；音乐扰动一个持续演化、具有记忆的人工物质，画面只是该物质状态的外显。**

开发时请遵守以下约束：

1. **先修数据语义与确定性，再做新视觉效果。**
2. 不要直接把 `crystalline / fluid / plasma` 写成三个互斥 preset。
3. Renderer 必须主要读取**连续状态变量与 phase weights**，而不是大量 `if phase == ...`。
4. `structure_type` 只能保留为**整首歌曲的弱全局 prior**，不能继续决定整首歌从头到尾的固定几何拓扑。
5. 不要为了“物理感”堆砌名词。没有拓扑荷就不要叫 Skyrmion；普通颜色映射不要叫 bandgap/laser/blackbody physics。
6. 不要求 CPU 与 GPU 像素级一致，只要求**语义状态一致（semantic parity）**。
7. 所有随机视觉必须可复现。实时播放、串行导出、并行导出、Seek 后重建都不能因为全局 RNG 而走出不同世界线。
8. 不要在 P0/P1 尚未完成时先写 Navier–Stokes、复杂 PDE、3D 粒子或大型 Shader 框架。
9. 不增加与核心目标无关的功能。
10. 每一阶段都应有自动测试和至少一个人工视觉验证入口。

---

# 1. 当前源码审计：已经做对了什么

以下属于 **[现状事实]**，来自当前上传源码。

## 1.1 音频分析层其实已经很丰富

`app/analysis/features.py` 中的 `FrameFeatureSequence` 已经定义 30 维 L1 特征：

- RMS
- Peak
- Loudness
- 6 个频段
- Spectral centroid
- Spectral rolloff
- Spectral bandwidth
- Spectral flatness
- Spectral flux
- Onset strength
- ZCR
- Harmonic energy
- Percussive energy
- 12 维 Chroma

当前 `FeatureFrame` 也已经进一步暴露了：

```python
chroma_vector
harmonic_e
percussive_e
flux
```

因此此前“视觉层缺信息”的问题已经开始被修复。

---

## 1.2 PhaseEngine 已经落地，但还只是第一版状态滤波器

当前：

```text
app/visual/phase_engine.py
```

已经产生：

```text
order_parameter
effective_temp
anisotropy
w_crystalline
w_hydrodynamic
w_plasma
phase_name
```

这是正确方向。

但目前所谓 hysteresis 实际主要由 attack/release 式低通产生，属于：

```text
inertia / relaxation
```

而不是严格意义上的：

```text
metastability / hysteresis / path dependence
```

同一输入保持数秒后，不同历史状态会快速收敛到同一个状态。

所以：

> 当前 PhaseEngine 可以保留作为 prototype，但不应视为 V2 最终动力学模型。

---

## 1.3 Chroma → PES → Particle 已经真正接通

当前数据链已经存在：

```text
FeatureFrame.chroma_vector
        ↓
PESField.update()
        ↓
sample_potential()
        ↓
sample_force()
        ↓
ParticleSystem.update()
```

因此 PES 不是纯文档概念。

这是整个新方向里最值得继续发展的部分之一。

---

## 1.4 但 PhaseState 目前几乎没有真正进入最终几何

当前：

```python
Scene.update(...)
    -> phase_engine.update(...)
    -> ring_layer.update(... phase_state=self.phase_state)
```

`RingLayer` 会保存 `phase_state`。

然而当前 `renderer.py` 的核心生成结构仍然主要依赖：

```python
dna.structure_type
```

并选择：

```text
reactor
vortex
organic
pulse
```

Phase weights 没有系统地控制这些几何层。

因此当前状态可以概括为：

```text
PhaseEngine 已装上
        ↓
PES 已部分接上粒子
        ↓
宏观 Renderer 仍是旧传动系统
```

这就是下一阶段真正需要打通的断点。

---

# 2. P0：继续开发前必须修的现有问题

下面这些问题优先级高于新增 Chladni、Fluid Shader、Plasma 等视觉效果。

---

## P0-1. Spectral centroid / rolloff 被二次归一化

### [现状事实]

在：

```text
app/analysis/spectrum.py:22-35
```

已经进行了：

```python
centroid / 8000.0
rolloff / 8000.0
```

并裁剪到 `[0,1]`。

但：

```text
app/visual/scene.py:134-135
```

又执行：

```python
centroid_norm = centroid / 7000.0
rolloff_norm = rolloff / 14000.0
```

这会把已经约为 `0~1` 的量再次压成近似 `1e-4`。

### [直接修复]

改为：

```python
centroid_norm = clamp(centroid, 0.0, 1.0)
rolloff_norm = clamp(rolloff, 0.0, 1.0)
```

并增加单元测试，确保：

```text
输入 0.5 -> 视觉控制仍约为 0.5
```

而不是 `~1e-4`。

### [注意]

修复后若旧视觉突然明显“更活跃”，这是正常的。不要为了恢复旧观感再次偷偷缩小输入，而应重新调整最终视觉层的 gain。

---

## P0-2. Spectral contrast 的量纲使用错误

### [现状事实]

`librosa.feature.spectral_contrast()` 输出不是 `[0,1]` 控制量，而当前代码：

```text
app/analysis/spectrum.py:146-150
```

得到 contrast 后，`extractor.py` 直接：

```python
global_contrast = np.mean(spectral_contrast_vec)
```

随后却使用：

```python
if global_contrast > 0.4:
if global_contrast > 0.45:
line_thickness = 1.2 + global_contrast * 4
```

`themes.py` 又有：

```python
saturation_scale = 1.1 + f.spectral_contrast * 0.2
```

这会使若干 branch 长期饱和。

### [建议]

不要在不看真实歌曲分布的情况下随便指定一个“神奇除数”。

先增加：

```text
scripts/audit_feature_ranges.py
```

对用户的一组代表性歌曲统计：

```text
P01 / P05 / P25 / P50 / P75 / P95 / P99
```

至少统计：

- spectral contrast
- RMS / loudness
- onset
- flux
- 6 band drive
- centroid
- flatness
- H/P ratio

然后定义明确的视觉归一化函数，例如：

```python
contrast_norm = smoothstep(low_db, high_db, contrast_db)
```

或固定的单调饱和函数。

**原始 contrast 与视觉 contrast 必须分开命名：**

```text
spectral_contrast_db_like
spectral_contrast_norm
```

不要再让同一个变量既代表音频特征原值，又代表 `[0,1]` UI/视觉控制量。

---

## P0-3. 当前所谓 bass/mid/high “全局比例”不是严格的频谱能量比例

### [现状事实]

`compute_band_energies_6()` 会对**每个频带分别按自己的最大值归一化**：

```python
x_norm = x / x.max()
```

之后 `_compute_globals_and_semantics()` 又对这些已经独立归一化的 band mean 求：

```python
b_ratio = b_mean / total
m_ratio = m_mean / total
h_ratio = h_mean / total
```

因此当前 `bass_ratio/mid_ratio/high_ratio` 更接近：

> 每个频段在整首歌中“相对自己最大值后的平均活跃程度比例”

而不是：

> 真正的跨频段能量占比。

### [风险]

这会污染：

- `structure_type`
- brightness/warmth 相关映射
- palette
- global fingerprint

并进一步压缩不同歌曲之间的结构差异。

### [建议]

保留两套量：

```text
band_drive_*     # 为每个频带单独归一化，用于动画响应
band_share_*     # 来自未独立归一化的谱能量，用于全局光谱平衡
```

例如从 `S_power` 直接计算：

```python
raw_band_power[k, t]
share[k, t] = raw_band_power[k, t] / sum(raw_band_power[:, t])
```

然后全局：

```python
global_band_share = weighted_mean(share, activity_weight)
```

不要删除现有 band drive，因为它很适合做实时动画。

---

## P0-4. 无法检测节拍时，不应伪造 120 BPM beat train

### [现状事实]

`app/analysis/beat.py:41-46`：

如果没有检测到 peak，当前代码会生成：

```python
0.5s, 1.0s, 1.5s, ...
```

也就是人工 120 BPM 节拍。

随后 `extractor.py` 又可能因为 beat 数量很多而得到较高 confidence。

### [后果]

Ambient、Drone、极静音乐、无节拍片段甚至某些失败分析结果，会被系统强行解释成：

```text
120 BPM + 高规则性
```

这会严重制造同质化。

### [必须修改]

如果检测失败：

```python
beat_times = np.array([])
beat_strengths = np.array([])
beat_confidence = 0.0
```

`tempo=120` 可以作为 UI fallback，但必须与：

```text
tempo_confidence = 0
```

区分。

任何视觉逻辑使用 tempo / beat regularity 时，都必须受 confidence gate 控制。

> “不知道节拍”不能等价于“这是一首稳定的 120 BPM 歌”。

---

## P0-5. Scene.reset() 没有重置 PhaseEngine / PESField

### [现状事实]

`app/visual/scene.py:296-313` 会重建：

- EffectState
- RingLayer
- EnergyCore

并清空 particles。

但不会重建：

```python
PhaseEngine()
PESField()
phase_state
```

### [风险]

切歌后，新歌可能继承上一首歌的 phase internal state。

### [修改]

`reset()` 必须包括：

```python
self.phase_engine = PhaseEngine()
self.pes_field = PESField()
self.phase_state = None
```

后续若引入 `MaterialStateEngine`，其全部内部状态也必须统一进入 reset contract。

---

## P0-6. 当前 PES 使用的是整首歌曲 global energy，而不是局部能量

### [现状事实]

`Scene.update()` 中：

```python
energy = self.global_features.energy
```

随后：

```python
self.pes_field.update(
    chroma_vector=...,
    energy=energy,
    flux=...
)
```

因此 `PESField.field_scale` 的主要 energy 项对一首歌而言基本是常数。

### [后果]

PES 在歌曲内部的动态主要依赖 flux 和 chroma，能量变化本身没有真正改变场强。

### [修改]

至少改成局部量，例如：

```python
local_energy = visual_context.energy_fast
```

或者迁移前临时使用：

```python
local_energy = self.audio_drive["rms"]
```

全局 energy 只能作为 prior，例如：

```python
field_gain_prior = 0.8 + 0.4 * global_energy
```

不能作为实时驱动主体。

---

## P0-7. 静音会产生“Hydrodynamic phase + 非零 vortex”

### [现状事实]

当前 PhaseEngine：

```python
harmonic_e = 0
percussive_e = 0
```

时：

```python
hpr ≈ 0
order_parameter -> 0
```

最后会向 `hydrodynamic` 收敛。

独立测试当前代码，长时间零输入会趋向：

```text
phase_name      = hydrodynamic
w_hydrodynamic ≈ 1
```

同时 `PESField`：

```python
vortex_strength = 0.2 + ...
```

即使输入能量接近 0，也保留常数 0.2。

如果 chroma 无有效输入，还会替换成 uniform chroma，而当前 angular mapping 并不保证 uniform chroma 对应零场。

### [建议]

引入独立的：

```text
activity ∈ [0,1]
```

低 activity 时：

- excitation 衰减；
- mobility 衰减；
- defect 缓慢愈合；
- order 可以缓慢 anneal；
- 场强趋近于 0；
- 不强行判定成 Fluid。

不要必须引入第四个完整 phase；可以只定义：

```text
dormant / low-activity regime
```

作为显示状态。

核心原则：

> **Activity 控制“这个世界现在被激发了多少”；Phase 控制“它处在什么结构状态”。**

两者不能混为一谈。

---

## P0-8. `PESField` 文档声称 analytical gradient，但实际仍是 finite difference

### [现状事实]

文件头写：

```text
analytical gradient forces
```

但 `sample_force()` 当前调用：

```python
V(x, y)
V(x+eps, y)
V(x, y+eps)
```

计算数值差分。

### [性能风险]

本次会话容器中，对当前代码做简单 microbenchmark：

```text
1600 particles × 1 次 sample_force
约几十 ms 量级
```

本环境粗测约 **49 ms**，这还没有包含 QPainter、粒子绘制、HUD、ring 等。

该数字不是跨机器 benchmark，但足以说明当前算法级别不应继续叠复杂度。

### [修改]

实现真正的解析梯度或 Fourier-compressed field，详见后文 PES 章节。

---

# 3. 另外几个应在 V2 过程中一起修正的数据问题

---

## 3.1 Frame feature rate 与 `FEATURE_FPS=60` 语义不一致

当前 L1 实际：

```python
frame_rate = sr / hop_length
```

在 44100 / 512 下约为：

```text
86.13 Hz
```

而 constants 里存在：

```python
FEATURE_FPS = 60
```

但不是 L1 真正采样率。

### 建议

删除或重新命名 `FEATURE_FPS`，不要让后续代码假设 L1 是 60 Hz。

明确区分：

```text
analysis_frame_rate ≈ 86.13 Hz
simulation_rate     = 60 Hz（若采用固定模拟步长）
render_rate         = 24/30/60/120... Hz
```

这三者必须独立。

---

## 3.2 Spectral centroid 最好确认到底采用 magnitude 还是 power weighting

当前 extractor 把：

```python
S_power
```

传给 spectral centroid。

这会比常见 magnitude-weighted centroid 更强调强峰。

这未必绝对错误，但必须明确语义。

### 建议

如果目标是传统 spectral centroid：

```python
compute_spectral_centroid(S_mag, ...)
```

如果刻意要 power centroid，就改名，避免“标准音频特征”与自定义量混淆。

---

## 3.3 Chroma 的全曲平均不应无权重地把静音/非调性段落混进去

当前：

```python
avg_chroma = np.mean(chroma_data, axis=0)
```

### 建议

至少按：

```text
harmonic energy × activity × tonal confidence
```

进行加权。

同时不要把：

```text
strongest chroma + secondary interval
```

解释成可靠的 major/minor 识别。

当前 hue mapping 可以作为艺术 fingerprint，但注释应更严谨。

---

# 4. L3 / L4 当前不能直接接进 PhaseEngine：必须先修时间语义

这是非常重要的一点。

---

## 4.1 当前 L3 window 是“从当前索引向未来取窗口”

`compute_rolling_stats()` 当前：

```python
start = i * hop_frames
end = start + window_frames
window = feature[start:end]
```

如果 `times_1hz[i] = i sec`，那么：

```text
time = 20s 的 8s window
实际上描述 20s ~ 28s
```

这意味着如果直接在 20s 使用该结果，视觉会提前知道未来 8 秒。

### 这不是绝对禁止

Stormy-Pulse 是离线预分析播放器，不是直播输入，所以技术上可以看未来。

但若视觉在副歌真正出现前几秒已经提前“升温/熔化”，听感会错位。

### V2 建议

默认使用**因果 trailing window**：

```text
2s: [t-2, t]
4s: [t-4, t]
8s: [t-8, t]
```

歌曲开头不足窗口时使用已有历史，不补未来。

---

## 4.2 不同 window 长度当前数组长度不同，但共用同一个 `times_1hz`

当前 `times_1hz` 取自 2s window 的长度。

8s window 比 2s window 更短。

`get_window_stats_at_time()` 在歌曲末尾请求 8s stats 时可能索引超界并返回 0。

### 修改

所有 window 输出应覆盖统一：

```text
t = 0 ... duration
```

并使用 trailing/padded rolling statistics，使 2/4/8s 数组长度一致。

---

## 4.3 当前 1 Hz window 值直接按整数秒索引，会产生阶梯

```python
idx = int(time)
```

后续如果把 L3 用于几何形变，会出现每秒一次的隐蔽 step。

### 修改

实现：

```python
get_window_stats_at_time()
```

的线性插值。

L3 本身只需 1~2 Hz 存储，没有必要提高缓存密度；播放时插值即可。

---

# 5. L4 section 应该是“弱结构 prior”，不能当歌曲语义真值

当前 section analysis：

- 只有 generic `Section 0/1/...`
- climax 主要基于 section RMS
- repeated sections 当前硬编码为空
- 并没有可靠 verse / chorus / bridge 语义

所以 V2 不要写：

```python
if section == "chorus":
    plasma()
```

应该只暴露：

```text
section_id
section_progress
section_age
boundary_impulse
novelty
section_energy_relative
climax_prior
```

用途是：

- section boundary 临时提高系统 susceptibility；
- novelty 允许更明显的 topology rearrangement；
- climax 只作为 excitation 的小幅 prior；
- section progress 控制慢速演化；
- 不直接强制 phase。

---

# 6. 推荐的新架构

建议新增一个与 Qt/Renderer 完全解耦的纯 Python 包：

```text
app/dynamics/
    __init__.py
    context.py
    calibration.py
    material.py
    trajectory.py
    field.py
    deterministic.py
```

原则：

```text
analysis 不能依赖 visual
dynamics 不能依赖 Qt
visual 可以依赖 dynamics
```

---

## 6.1 推荐数据流

```text
Audio File
   │
   ▼
FeatureExtractor
   │
   ├── L1 Frame Features
   ├── L2 Events
   ├── L3 Causal Windows
   ├── L4 Structure
   └── L5 Global Priors
   │
   ▼
TrackCalibration
   │
   ▼
VisualContextBuilder
   │
   ▼
MaterialTrajectoryCompiler
   │
   ▼
MaterialStateSequence
   │
   ├─────────────┐
   ▼             ▼
FieldModel     Renderer Controls
   │             │
   ▼             │
Particles ◄──────┘
   │
   ▼
Final Frame
```

---

# 7. 不建议把完整 30D 特征直接继续塞进 FeatureFrame

当前 `FeatureFrame` 是兼容层。

如果继续不断加：

```text
low_mid
high_mid
presence
zcr
bandwidth
2s...
4s...
8s...
section...
```

最终 Scene 会变成一个巨型 feature soup。

### 推荐

保留：

```python
FeatureCache.frame_seq
```

作为原始/低层数据源。

新增：

```python
VisualContextBuilder
```

输出明确语义的视觉输入。

---

# 8. VisualContext 设计

建议第一版只保留真正会参与动力学的量，不要为了“全面”塞几十个字段。

示例：

```python
@dataclass(frozen=True)
class VisualContext:
    time: float

    # Activity / energy
    activity: float
    energy_fast: float
    energy_slow: float
    energy_trend: float

    # Spectrum
    bass_drive: float
    mid_drive: float
    high_drive: float
    spectral_brightness: float
    spectral_noise: float
    spectral_tilt: float

    # Rhythm / transient
    onset: float
    flux: float
    beat_impulse: float
    beat_confidence: float
    transient_density: float
    beat_density: float

    # Tonal structure
    harmonic_ratio: float
    tonal_confidence: float
    chroma: np.ndarray

    # Macro structure
    novelty: float
    boundary_impulse: float
    climax_prior: float
    section_progress: float
```

### 不要使用含糊变量名

当前：

```text
anisotropy
effective_temp
```

容易让人误以为有严格物理定义。

推荐内部逐步改为：

```text
spectral_tilt
excitation
```

如需兼容 HUD：

```python
effective_temp = excitation  # deprecated alias
```

---

# 9. TrackCalibration：解决“不同母带响度”和 peak normalization 的问题

当前很多特征：

```text
/ max(track)
```

会被单个极端峰值控制。

同时原始 RMS 又会受到母带响度影响。

V2 应区分：

```text
absolute-ish signal presence
track-relative dynamics
```

---

## 9.1 RMS 建议使用 dB 域

先：

\[
L(t)=20\log_{10}\frac{\mathrm{RMS}(t)+\epsilon}{\max(\mathrm{RMS})+\epsilon}
\]

得到相对于全曲峰值的 dB。

然后：

```text
activity
```

用于判断是否真正有信号。

`energy_fast` 则使用歌曲内部 robust percentile。

例如：

\[
x_\mathrm{rel}
=
\mathrm{clip}
\left(
\frac{x-P_{10}}{P_{95}-P_{10}+\epsilon},
0,1
\right)
\]

具体 P10/P95 不必迷信，应该由测试曲库分布调整。

---

## 9.2 Flux / onset 不应只用全曲 max

单次异常峰值会压低整首歌其余 transient。

建议：

```text
P95 / P98 normalization
```

并允许大于高 percentile 的输入饱和。

---

## 9.3 需要保存 calibration metadata

例如：

```python
@dataclass
class TrackCalibration:
    rms_db_p10: float
    rms_db_p95: float
    flux_p95: float
    onset_p95: float
    contrast_low: float
    contrast_high: float
```

注意：

> Calibration 属于音频特征语义，而 Material/Phase 参数属于视觉模型语义。两者版本应分离。

---

# 10. 最重要的架构决定：Material trajectory 建议预编译，而不是绑定 Renderer FPS 在线积分

当前：

```python
PhaseEngine.update(... dt=renderer_dt)
```

也就是说 phase dynamics 与 render FPS 绑在一起。

即使代码试图用 `dt` 修正，一阶 Euler、事件采样、状态 smoothing 等仍可能使：

```text
30 FPS
60 FPS
120 FPS
```

产生不同轨迹。

这对于：

- 视频导出；
- Seek；
- 并行分段；
- CPU/GPU 切换；

都非常麻烦。

---

## 10.1 推荐方案

Stormy-Pulse 当前处理的是**完整音频文件**，不是 live microphone。

因此可以在音频分析完成后，快速从头积分一次人工物质状态：

```text
FeatureCache
    ↓
VisualContextSequence
    ↓
MaterialTrajectoryCompiler
    ↓
MaterialStateSequence
```

例如以：

```text
60 Hz
```

或直接 analysis frame rate 积分。

然后播放时：

```python
state = material_sequence.get_state_at_time(t)
```

直接插值。

---

## 10.2 这样会立即解决

### Seek

直接查询任意 `t`，不会继承 Seek 前的错误 phase state。

### 30/60 FPS

Material state 与 render FPS 无关。

### Parallel export

各 worker 在同一个 t 得到完全相同 material state。

### GPU/CPU

两套 renderer 读取同一 state。

### Hysteresis

即使有几十秒的记忆，也不需要每次 Seek 从歌曲开头重新计算。

---

## 10.3 不建议把 MaterialStateSequence 立即混进昂贵的 audio cache

Phase 模型开发阶段会频繁变化。

如果每调一次视觉参数就 bump 整个 audio cache，用户会被迫重新跑 librosa/HPSS。

### 推荐版本拆分

```text
AUDIO_CACHE_VERSION
DYNAMICS_VERSION
```

第一阶段甚至可以：

```text
音频特征照常缓存
MaterialTrajectory 每次 load 后在内存快速编译
```

因为几十万个 scalar 运算远比重新提取音频特征便宜。

等模型稳定以后，再考虑单独缓存 material trajectory。

---

# 11. MaterialStateEngine：建议从“假温度分类器”升级成真正有记忆的人工材料

建议最终状态至少包含：

```python
@dataclass
class MaterialState:
    order: float
    excitation: float
    mobility: float
    defect_density: float

    w_crystalline: float
    w_hydrodynamic: float
    w_plasma: float

    activity: float
```

这已经足够。

不要第一版就上十几个 order parameter。

---

# 12. 推荐的动力学思路：用 Defect 产生真正 path dependence

当前 smoothing 的问题是：

> 不同历史最终很快忘掉。

最简单且视觉上合理的真正记忆变量就是：

```text
defect_density
```

---

## 12.1 Excitation

目标：

```python
excitation_target = (
    0.35 * energy_fast
    + 0.25 * flux
    + 0.20 * onset
    + 0.20 * transient_density
)
```

这里只是建议初值，不是神圣公式。

用时间常数而不是 frame-based coefficient：

\[
\alpha = 1-e^{-\Delta t/\tau}
\]

```python
excitation += (target - excitation) * alpha
```

升温快，冷却慢：

```text
tau_attack  < tau_release
```

---

## 12.2 Order drive

例如：

```python
order_drive = (
    tonal_confidence
    * (1 - spectral_noise)
    * (0.35 + 0.65 * harmonic_ratio)
)
```

再由 defect 抑制：

```python
order_target = order_drive * (1 - defect_density)
```

---

## 12.3 Defect creation / healing

事件与高 excitation 快速制造缺陷：

```python
damage = (
    0.45 * onset
    + 0.35 * flux
    + 0.20 * excitation
)
```

例如：

```python
d_defect += create_rate * damage * (1 - defect) * dt
```

但修复很慢：

```python
d_defect -= heal_rate \
            * (1 - excitation) \
            * order_drive \
            * defect \
            * dt
```

于是：

```text
强烈高潮之后
即使音乐已经回到中等能量
defect 仍然较高
```

因此画面不会瞬间恢复。

这就是我们真正需要的：

```text
history dependence
```

---

## 12.4 Mobility

可以由：

```text
excitation
rhythmic flow
beat density
defect
```

共同控制。

Fluid 不是“中间 temperature 的默认垃圾桶”，而应真正表现为：

```text
结构不完全无序
但粒子/场具有较高迁移能力
```

---

# 13. Phase weights：连续 soft assignment，不要硬切 preset

可为三个视觉物态设置 prototype：

```text
Crystal:
    order high
    excitation low
    mobility low
    defects low

Fluid:
    order medium
    excitation medium
    mobility high
    defects medium

Plasma:
    order low
    excitation high
    mobility high
    defects high
```

计算 state 到三个 prototype 的距离：

\[
d_i^2
=
\sum_j
w_j(x_j-\mu_{ij})^2
\]

然后：

\[
p_i =
\frac{e^{-\beta d_i^2}}
{\sum_k e^{-\beta d_k^2}}
\]

这样天然得到：

```text
w_crystalline + w_hydrodynamic + w_plasma = 1
```

`phase_name` 只用于：

- debug
- HUD
- 日志

Renderer 不应该主要读取 `phase_name`。

---

# 14. Silence / dormant 的具体策略

当：

```text
activity < activity_gate
```

不要让缺失的 harmonic energy 被解释成“无序流体”。

建议：

```text
excitation -> 0
mobility   -> 0
defect     -> 缓慢 heal
order      -> 缓慢 anneal 到较高值
```

但最终画面强度乘：

```text
activity / idle_visibility
```

这样：

> 静音时可以留下一个非常淡的、有序、休眠中的结构，而不是无缘无故变成流体漩涡。

---

# 15. L3 / L4 应如何真正影响 Material dynamics

建议影响的是**动力学参数**，而不是直接切换画面。

---

## L3 2s：短时局部环境

用途：

```text
energy_fast
transient_density
短时 trend
```

控制：

- excitation attack
- defect creation
- burst susceptibility

---

## L3 4s：中时 groove

用途：

```text
beat_density
energy mean
spectral activity
```

控制：

- mobility
- fluid tendency
- persistent circulation

---

## L3 8s：慢背景

用途：

```text
energy_slow
brightness trend
chaos proxy
```

控制：

- baseline state
- annealing rate
- macro phase bias

---

## L4 boundary / novelty

不要：

```text
boundary -> plasma
```

而是：

```text
boundary -> temporarily lower structural barrier
```

视觉解释：

> 段落变化时，材料更容易重排。

这可以表现为：

```python
susceptibility = base + novelty * k
```

使同样一个 onset 在 section transition 附近造成更大的 topology change。

---

# 16. PES / Field V2：当前最值得深挖的部分

## 16.1 首先明确物理语言

如果：

\[
\mathbf F = -\nabla V
\]

这是 conservative potential force。

但 vortex/curl force 一般不能写成同一个 scalar potential 的梯度。

因此文档应明确：

\[
\mathbf F_{\text{total}}
=
\mathbf F_{\text{potential}}
+
\mathbf F_{\text{curl}}
+
\mathbf F_{\text{stochastic}}
\]

不要把整个混合场都叫：

```text
-PES gradient
```

---

# 17. Chroma topology：建议改成 circle-of-fifths / Fourier field

当前：

```python
theta * (1 + k % 4) + k*pi/6
```

实际上是让 12 个 chroma 权重混合控制 `m=1..4` angular Fourier modes。

这作为 generative art 没问题，但它不是字面意义的：

> 12 个 pitch class 对应 12 个 angular wells。

所以需要二选一：

### A. 保留 Fourier 艺术模型

那就诚实命名：

```text
chroma-driven angular mode field
```

### B. 做真正的 pitch topology

我更推荐 B，并使用 **circle of fifths** 排列，而不是 chromatic 0,1,2,3... 顺序。

例如：

```python
circle_index = (7 * pitch_class) % 12
theta_k = 2*pi*circle_index/12
```

这样和声关系较近的 pitch class 在场空间也更接近。

---

# 18. 不建议直接用 12 个独立 expensive wells；建议先压成 Fourier coefficients

对 chroma：

\[
w_k
\]

以及 pitch angle：

\[
\theta_k
\]

预计算：

\[
C_m
=
\sum_{k=0}^{11}
w_k e^{-im\theta_k}
\]

只保留：

```text
m = 1...4
```

或最多：

```text
1...6
```

则：

\[
V(r,\theta)
=
g(r)
\sum_m
a_m
\operatorname{Re}
\left(
C_m e^{im\theta}
\right)
+
V_r(r)
\]

好处：

1. `update()` 时只处理一次 12 chroma。
2. 每个 particle sampling 不再循环 12 notes。
3. 可直接得到解析：
   - \(\partial V/\partial r\)
   - \(\partial V/\partial\theta\)
4. 非常适合未来传入 GLSL uniform。

本会话中做的简单 Python prototype，相对当前 finite-difference + 12-loop 实现有约数倍级速度提升；实际项目仍需在目标机器 benchmark。

---

# 19. Tonal confidence：避免噪声/静音也制造“和声势阱”

定义 chroma probability：

\[
p_k = \frac{w_k}{\sum w}
\]

entropy：

\[
H=-\sum_k p_k\ln p_k
\]

归一化：

\[
H_n = H/\ln 12
\]

可以构造粗略：

\[
C_{\rm tonal}=1-H_n
\]

然后结合 harmonic energy/activity。

当：

```text
tonal_confidence -> 0
```

chroma potential amplitude 应趋向 0。

不要：

```text
无 chroma -> uniform chroma -> 仍然生成强结构场
```

---

# 20. Chroma 必须时间平滑

逐帧 CQT/chroma 会抖。

建议对 normalized chroma 做：

```text
100~300 ms
```

量级 smoothing。

不要每帧突然重构整个 potential landscape。

但 onset/section boundary 可以暂时加快 topology adaptation，形成：

> 平时缓慢变形，和弦/段落突变时快速重排。

---

# 21. Phase 应直接改变 force decomposition

当前无论 phase 如何，粒子都收到近似相同的：

```text
gradient + vortex
```

这是错误的。

推荐：

\[
\mathbf F =
w_c K_c\mathbf F_{\rm potential}
+
w_f K_f\mathbf F_{\rm curl}
+
w_p K_p\mathbf F_{\rm stochastic}
\]

同时 drag 也变化。

---

## Crystal

```text
potential force  ↑
curl             ↓
noise            ↓
drag             ↑
site locking     ↑
```

粒子倾向驻留在势阱/规则轨道。

---

## Fluid

```text
potential        medium
curl             ↑↑
drag             medium
advection        ↑
noise            low-medium
```

粒子成为 tracer。

---

## Plasma

```text
potential coherence ↓
curl                medium
stochastic kicks    ↑↑
defect scattering   ↑
drag                 ↓
short transient     ↑
```

这样三个 phase 才真正是**同一粒子世界的三种运动规律**，不是三套贴图。

---

# 22. Geometry：这是解决同质化最关键的一层

现在的最大断点不是 PhaseEngine，而是：

> Renderer 仍然在画旧的结构。

V2 的核心必须是：

```text
MaterialState
      ↓
Geometry Parameters
      ↓
One continuously morphing world
```

---

# 23. 建议建立统一的 GeometryControl

例如：

```python
@dataclass
class GeometryControl:
    symmetry: float
    coherence: float
    angular_lock: float
    curvature: float
    circulation: float
    fragmentation: float
    defect_strength: float
    roughness: float
    radial_order: float
```

从 material state 推导：

```python
symmetry       ~ order * (1 - defect)
coherence      ~ order * (1 - 0.5*excitation)
circulation    ~ w_fluid * mobility
fragmentation  ~ defect * (0.4 + 0.6*w_plasma)
roughness      ~ w_plasma * excitation
angular_lock   ~ w_crystalline
```

Renderer 不需要知道复杂音频特征。

---

# 24. 推荐统一的基础曲线，而不是三个完全独立 Renderer

可以把主要 shell 写成：

\[
r(\theta)
=
R
+
\sum_m A_m
\cos(m\theta+\phi_m)
+
\delta r_{\rm defect}
+
\delta r_{\rm flow}
\]

然后：

### Crystal

- 少数稳定整数 mode
- phase locking
- 高对称
- segment coherence 高

### Fluid

- mode phase 随角度/时间连续 warp
- circulation
- 曲线拉伸
- 结构仍连续

### Plasma

- mode coherence 下降
- segment break
- defect/dislocation
- 随机但有时间相关的 roughness

于是：

```text
Crystal → Fluid → Plasma
```

真的是同一个几何对象发生相变。

---

# 25. 现有 reactor / vortex / organic / pulse 怎么办？

不要全部删除。

把它们从：

```text
hard structure selector
```

降级成：

```text
global style basis / prior
```

短期兼容方案：

```python
style_prior = dna.structure_type
```

但 phase/material controls 必须对所有 style 生效。

中期可以改成：

```python
StylePriorWeights(
    reactor=...,
    vortex=...,
    organic=...,
    pulse=...,
)
```

整首歌只决定世界的“先天材质偏好”，而不是从头到尾锁死拓扑。

---

# 26. RingLayer 里已经有一个很好用但当前基本空置的接口：broken_segments

当前：

```python
self.broken_segments
```

存在，但没有真正的 defect dynamics 驱动。

可以直接利用：

```text
defect_density
onset impulse
section novelty
```

产生可恢复的：

- segment crack
- missing arc
- phase slip
- dislocation-like offset

但注意：

> 如果只是随机删一段线，请叫 defect/fracture，不要声称是严格晶体位错模拟。

---

# 27. Chladni 放在哪一层最合适？

**不要把 Chladni 当成一个独立 preset。**

如果要做，建议把它作为高 order / 高 harmonicity 下的：

```text
nodal resonance geometry basis
```

即：

```text
w_crystalline ↑
tonal_confidence ↑
harmonic_ratio ↑
```

时，基础 geometry 的 nodal component 增强。

当流体化时：

```text
nodal lines warp
```

当 plasma 化时：

```text
nodal coherence breaks
```

这样不会再次陷入：

```text
quiet = Chladni preset
groove = fluid preset
climax = plasma preset
```

---

# 28. Color：不要再让物理名词承担不必要的责任

当前 `themes.py` 已经有较成熟的 scientific palette 体系。

建议继续以：

```text
global fingerprint -> base palette
```

为主。

Material state 只做有限调整：

```text
excitation   -> luminance / emission strength
order        -> palette purity / coherence
defect       -> accent dispersion
plasma       -> highlight width / local desaturation or hot accents
```

不要宣传：

```text
Bandgap color
Laser emission
Blackbody radiation
```

除非真的实现对应物理模型。

当前 `blackbody_radiation_color()` 如果只是视觉 utility，可以保留，但 README 应写：

```text
temperature-inspired color mapping
```

而不是模拟真实黑体谱。

---

# 29. “Skyrmion”建议暂时删除

除非未来明确构造：

```text
n(x,y)
```

这样的向量 order-parameter field，并计算 winding/topological charge。

普通 vortex/curl stream line 建议叫：

```text
vortex texture
topological-inspired flow texture
curl field
```

不要直接叫 Skyrmion。

---

# 30. 确定性 RNG：这是后续并行导出的生命线

当前多个模块直接使用全局：

```python
random.random()
random.uniform()
```

包括：

- Scene particle emission
- ParticleSystem
- EffectState camera shake
- Renderer high-frequency spikes
- EnergyCore offsets

`set_track_info()` 虽然注释写：

> seed all visual randomness

但实际上只临时 seed 后生成 `_grain_points`，然后恢复 global random state。

因此整个 simulation 并没有真正 seed。

---

# 31. 不要只做一个 stateful `random.Random(seed)` 就结束

单纯：

```python
rng = random.Random(track_seed)
```

虽然比现在好，但**并行 segment 从中途开始时仍然不知道 RNG 应该处于哪一步**。

推荐把随机分两类。

---

## 31.1 Simulation randomness

优先使用**按时间/事件索引确定的 stateless randomness**：

```text
(track_seed, stream_id, simulation_tick, event_index, particle_index)
    ↓
deterministic_hash
    ↓
0...1
```

例如：

```text
beat burst particle angle
ambient emission decision
plasma kick
camera shake direction
```

都由固定 key 产生。

这样：

> 从 100s 开始重放，不需要知道 0~100s 消耗过多少 random number。

---

## 31.2 Render-only randomness

例如当前 `_draw_atmosphere_layer()` 每帧随机生成 spike angle。

不要让 draw call 消耗 simulation RNG。

改为：

```text
hash(track_seed, frame_index, spike_index)
```

这样：

- HUD 开关不会改变物理世界；
- CPU/GPU 切换不会改变 particle RNG；
- 重绘同一帧不会出现不同随机线条。

---

## 31.3 不要使用 Python 内置 `hash()`

Python `hash()` 默认跨进程可能有随机化。

使用稳定方法，例如：

```text
BLAKE2
SplitMix64
PCG seed derivation
```

---

# 32. Seek：当前实现对于长期动力学是不完整的

### [现状事实]

`MainWindow._on_seek()` 当前只：

```python
audio_player.seek(...)
visualization_sync.seek_to(...)
```

`Scene.update()` 发现时间倒退时只重置：

```python
last_onset_time
```

不会重建：

- particles
- ring state
- effects
- phase history
- material state
- random state

因此当前 Seek 后已经可能出现：

> 40s 的音频 + 180s 遗留下来的粒子/状态。

---

# 33. 推荐 Seek 架构

如果 MaterialTrajectory 已预编译：

```text
material state
```

可直接查询，无需回放。

粒子与短期效果仍然 stateful。

第一版可以：

```text
Seek 到 t
    ↓
清空 transient particles/effects
    ↓
从 max(0, t - warmup) 开始固定步长快速模拟
    ↓
到达 t
```

例如 warmup 5~8s。

这会牺牲更早产生的长寿粒子，但当前 particle lifetime 本身大致是秒级，视觉上可接受。

后续如确实增加长寿结构，再引入 checkpoint。

---

# 34. Parallel export：长期 phase memory 不应依赖 preroll 恢复

当前每个 worker：

```text
从 segment start 前 5~8s warmup
```

然后开始渲染。

对于当前短记忆 phase 还能勉强工作。

但如果未来真正有几十秒 hysteresis：

```text
5s preroll 不可能恢复 MaterialState
```

因此：

> **Material trajectory 必须预计算/可随机访问。**

这样 preroll 只负责：

- particles
- short effects
- ring envelopes

而不是负责恢复宏观物态。

---

# 35. 固定 simulation step：避免不同 FPS 产生不同粒子世界

当前大量逻辑使用：

```python
sf = dt * 60
```

这比完全按 frame 写死好，但仍不是严格 frame-rate independent。

例如：

```python
x += (target-x) * rate * sf
```

在低 FPS 下可能 overshoot。

ambient emission 又是：

```python
if random() < emit_chance:
```

每帧一次，因此 30 FPS 与 60 FPS 的单位时间 emission 数不同。

---

## 推荐

### 连续 smoothing

统一 helper：

```python
def exp_smooth(current, target, tau, dt):
    alpha = 1.0 - exp(-dt / tau)
    return current + (target-current) * alpha
```

### Drag

```python
v *= exp(-drag_lambda * dt)
```

### Ambient stochastic rate

如果期望每秒 rate 为 \(\lambda\)：

\[
p(\Delta t)=1-e^{-\lambda \Delta t}
\]

不要使用固定每帧概率。

### 最终

最好让粒子/scene simulation 使用：

```text
fixed 60 Hz simulation tick
```

Renderer 可以 24/30/60/120 FPS。

---

# 36. CPU / GPU 的正确分工

## CPU 必须负责

- audio feature lookup
- VisualContext
- precompiled MaterialState
- phase weights
- section logic
- deterministic seeds
- 少量几何参数

这些计算极轻，不需要 Shader。

---

## GPU 最适合负责

- 大量 particle integration
- dense vector field
- field sampling
- glow/compositing
- 高密度 nodal field
- future phase-field texture

---

## 当前 GPU 现状

`app/visual_gpu/gl_scene_widget.py`：

```python
initializeGL():
    pass
```

`paintGL()` 仍然使用：

```python
QPainter
VisualizerRenderer bridge
```

所以当前应称为：

```text
OpenGL-backed migration scaffold
```

而不是真正 shader renderer。

### 结论

**现在不要为了 PhaseEngine 修改 GPU。**

先把 CPU 语义模型做好。

真正迁移时：

```text
MaterialState + FieldCoefficients
            ↓
         GLSL uniforms
```

即可。

---

# 37. CPU/GPU 不要求 100% feature parity

正确目标：

```text
同一首歌
同一时间 t
同一 VisualContext
同一 MaterialState
同一 phase weights
```

CPU 可以：

```text
解析曲线
较少粒子
近似 field
```

GPU 可以：

```text
dense field
更多粒子
更复杂 glow
```

只要宏观状态一致即可。

---

# 38. Cache 设计需要顺手清理的工程债

## 38.1 `CACHE_EXT=".npz"` 但实际内容是 gzip + pickle

这是命名误导。

短期不必阻断 V2，但之后建议改成真实扩展，例如：

```text
.spulse-cache
.pkl.gz
```

或者未来改用明确的 npz/json 组合。

---

## 38.2 Pickle cache 不能被视为不可信输入

`pickle.load()` 可以执行任意对象反序列化逻辑。

如果 cache 只由本机程序生成，风险较低。

README/代码不要鼓励用户交换来路不明的 cache 文件。

---

## 38.3 metadata cache version 不应硬编码 `"v4"`

当前 extractor 里 metadata 使用字符串：

```python
cache_version="v4"
```

而 constants 里另有：

```python
CACHE_VERSION = "v4"
```

改为单一来源。

---

## 38.4 当前“portable hash”注释与验证逻辑不完全一致

cache key 使用 filename/size/mtime，但 `_verify_cache()` 又要求：

```python
data["file_path"] == file_path
```

所以把同一 cache 移到另一台机器/另一目录并不真正 portable。

这不影响 V2 核心，但建议修正文档或逻辑。

---

# 39. Audio cache 与 Dynamics version 必须分离

推荐：

```python
AUDIO_CACHE_VERSION = "v5"
DYNAMICS_VERSION = "material-v2"
```

以下修改需要 bump audio cache：

- beat fallback semantics
- L3 causal windows
- raw band share
- 若修改 centroid 的定义

以下修改**不应**要求重新跑昂贵音频分析：

- phase prototype
- defect rates
- PES force constants
- geometry mapping

否则 vibe 阶段每改一次视觉模型都重新 HPSS，会非常痛苦。

---

# 40. 测试架构目前还有一个隐藏耦合

在本会话最小环境尝试只运行：

```text
tests/test_phase_engine.py
tests/test_pes_field.py
```

时，导入：

```python
app.visual.phase_engine
```

会先执行：

```text
app/visual/__init__.py
```

而该文件 eagerly import：

```python
VisualizerRenderer
```

继而要求 PySide6。

也就是说：

> 一个纯数学 PhaseEngine 单测，被 GUI dependency 绑住。

项目完整环境有 PySide6 时未必失败，但依赖方向不干净。

### 推荐

把纯动力学移入：

```text
app/dynamics/
```

其 `__init__.py` 不 import Qt。

这样 headless CI 可以独立测试。

---

# 41. 测试矩阵：必须新增的自动测试

## 41.1 Normalization

### centroid / rolloff

```text
输入 0.5
输出仍应在合理中间范围
```

### contrast

确保：

```text
finite
0 <= contrast_norm <= 1
```

且不同 synthetic spectrum 顺序合理。

### band share

确保：

```text
sum(shares) ≈ 1
```

---

## 41.2 Silence

输入长时间静音：

- 不出现 fake beats；
- beat confidence = 0；
- field amplitude -> 0；
- excitation -> 0；
- 无 NaN；
- 不被强迫变成 hydrodynamic。

---

## 41.3 Synthetic audio categories

至少：

```text
pure harmonic tone/chord
percussive click train
white noise
bass-heavy signal
high-frequency signal
silence
```

不要求它们对应“真实音乐类型”，只用于验证方向性。

---

# 42. 真正 Hysteresis 测试

构造：

```text
Path A:
长期 ordered input
    ↓
相同 middle input

Path B:
长期 high-excitation input
    ↓
相同 middle input
```

在进入 middle input 后的一段合理时间内：

```text
state_A != state_B
```

尤其：

```text
defect_A < defect_B
order_A  > order_B
```

这才证明存在真正历史依赖。

不能只测试：

```text
high energy -> plasma
low energy -> crystal
```

那只是分类器。

---

# 43. Frame-rate independence 测试

同一个 context trajectory：

分别以：

```text
30 Hz
60 Hz
120 Hz
```

采样/渲染。

最终 material trajectory 在同一绝对时间应一致到小容差。

如果 MaterialStateSequence 预编译，这个测试天然容易通过。

---

# 44. Seek equivalence 测试

定义：

```text
A:
从 0 顺序播放到 120s

B:
直接 seek 到 120s 并执行规定 warmup/rebuild
```

比较：

### 必须非常接近

- MaterialState
- phase weights
- geometry control

### 粒子

第一版允许不是逐粒子 bit-identical，但宏观统计必须合理：

```text
particle count
mean radius
velocity distribution
```

如果后续完成 deterministic event-key RNG，则可以进一步要求更严格一致。

---

# 45. Serial / parallel export seam 测试

在 segment boundary：

```text
serial raw frame
parallel raw frame
```

比较至少：

- MaterialState 完全一致；
- phase weights 完全一致；
- geometry parameters 完全一致；
- raw QImage 差异应足够小。

最终目标是在取消编码差异后，边界肉眼不可见。

---

# 46. PES 单元测试不应只检查“不是 NaN”

当前 test 主要检查：

```text
返回 float
不是 NaN
```

V2 增加：

### Conservative gradient consistency

随机点：

```text
analytic gradient
vs
small finite difference reference
```

两者应在容差内一致。

### Symmetry

给定对称 chroma，检查对应 field symmetry。

### Tonal confidence zero

```text
tonal_confidence=0
```

时：

```text
chroma potential contribution ≈ 0
```

### Center safety

`r -> 0` 时：

- 无 division by zero
- 无 NaN
- force bounded

---

# 47. 性能测试

不要把某一台机器的 ms 写成绝对产品要求。

推荐相对预算：

1. `VisualContext + MaterialState lookup` 应可忽略，相比一帧绘制远小于 1 ms。
2. PES V2 相比当前 numerical finite difference 至少有明显倍数级加速。
3. 1600 particles 场力计算不应单独吞掉 60 FPS 全部 16.7 ms frame budget。
4. 如果 CPU field 仍过重：
   - 减少 mode 数；
   - batch/vectorize；
   - 预计算 coarse field grid；
   - 或只对部分 particle 使用 field。
5. 不要在 Python per-particle loop 中继续叠更多 12/24/64 重 trig term。

---

# 48. 建议增加一个“Feature / Dynamics Inspector”开发脚本，而不是新 UI 功能

不要先往正式 GUI 塞 debug panel。

增加：

```text
scripts/audit_feature_ranges.py
scripts/plot_material_trajectory.py
```

它们可以输出：

```text
feature percentile
phase occupancy
order/excitation/defect over time
phase-space trajectory
section boundary overlay
```

这样开发者可以快速判断：

> 不同歌曲是否真的走出了不同相空间轨迹。

这是比“肉眼盯着酷不酷”更可靠的调参方式。

---

# 49. 反同质化的量化验证

选一组用户实际会听的歌曲，例如：

```text
Classical piano
Vocal pop
Rock/metal
Electronic
Ambient
Jazz/complex rhythm
Bass-heavy
Sparse acoustic
```

不需要写 genre classifier。

只把它们作为测试 corpus。

对每首歌计算：

```text
phase occupancy:
    mean w_crystal
    mean w_fluid
    mean w_plasma

trajectory:
    area / spread in (order, excitation)
    defect mean/max
    mobility distribution

transition:
    number of meaningful topology transitions
    mean dwell time
```

### 目标不是

让每个 genre 被固定映射到一个 phase。

### 目标是

确认：

> 不同歌曲的轨迹统计确实不同，同时同一首歌内部不同段落也有结构变化。

---

# 50. 不要过拟合 genre

非常重要。

错误做法：

```text
classical -> crystal
pop       -> fluid
metal     -> plasma
```

这只是新的 preset 系统。

正确做法：

```text
局部音乐结构驱动状态
全局特征只改变参数先验
```

一首古典作品高潮时完全可以熔化。

一首 metal 的安静 intro 也可以高 order。

---

# 51. 开发实施顺序

以下顺序建议严格执行。

---

## Phase 0 — Stabilize current semantics

### 0.1 修 centroid / rolloff 二次归一化

文件：

```text
app/visual/scene.py
```

### 0.2 修 spectral contrast normalization

文件：

```text
app/analysis/spectrum.py
app/analysis/extractor.py
app/visual/themes.py
```

先统计真实分布，再确定映射。

### 0.3 修 fake 120 BPM beats

```text
app/analysis/beat.py
app/analysis/extractor.py
```

### 0.4 分离 raw spectral band share 与 visual band drive

```text
app/analysis/spectrum.py
app/analysis/extractor.py
```

### 0.5 Scene reset 必须重置新动力学状态

```text
app/visual/scene.py
```

### 0.6 PES 使用 local energy + activity gate

### 0.7 增加 P0 regression tests

**完成标准：**

- 不添加新酷炫 geometry；
- 旧 UI/播放/导出正常；
- 当前已有视觉不出现明显 regression；
- 特征数值语义正确。

---

# 52. Phase 1 — VisualContext

新增：

```text
app/dynamics/context.py
app/dynamics/calibration.py
```

### 1.1 修 L3 为 causal window

### 1.2 所有 2/4/8s stats 覆盖统一时间轴

### 1.3 实现 window interpolation

### 1.4 建立 `VisualContextBuilder`

### 1.5 Scene 不再自己随意拼：

```python
brightness * 0.58 + high * 0.42
```

这类 mapping 应逐步集中到 context/control 层。

**完成标准：**

给任意 `t`：

```python
context = context_builder.at(t)
```

能返回稳定 `[0,1]` 语义控制量。

---

# 53. Phase 2 — Material Dynamics V2

新增：

```text
app/dynamics/material.py
app/dynamics/trajectory.py
```

### 2.1 引入

```text
order
excitation
mobility
defect_density
activity
```

### 2.2 使用 time-constant dynamics

### 2.3 实现真正历史依赖

### 2.4 soft phase weights

### 2.5 预编译 MaterialStateSequence

### 2.6 phase_name 仅用于 debug

**完成标准：**

- hysteresis test 通过；
- silence test 通过；
- 30/60/120fps lookup 一致；
- Seek 可直接获得正确 material state。

---

# 54. Phase 3 — Field / PES V2

将当前：

```text
app/visual/pes_field.py
```

逐步迁到纯 math：

```text
app/dynamics/field.py
```

### 3.1 chroma smoothing

### 3.2 tonal confidence

### 3.3 circle-of-fifths mapping

### 3.4 Fourier coefficients

### 3.5 analytical gradient

### 3.6 conservative / curl / stochastic 分离

### 3.7 phase weights 控制 force decomposition

**完成标准：**

- analytic gradient test；
- field silence test；
- current implementation 的明显性能提升；
- crystal/fluid/plasma 对同一粒子系统产生肉眼不同的运动规律。

---

# 55. Phase 4 — Renderer topology morph

修改：

```text
app/visual/ring_layer.py
app/visual/renderer.py
app/visual/particles.py
app/visual/energy_core.py
```

### 4.1 GeometryControl

### 4.2 phase weights 进入 harmonic shell

### 4.3 phase weights 进入 generative structure

### 4.4 defect_density 进入 segment continuity

### 4.5 mobility 进入 flow

### 4.6 plasma 进入 fragmentation / stochastic emission

### 4.7 `structure_type` 降级为 prior

**完成标准：**

一首歌内部出现连续：

```text
ordered
→ distorted
→ flowing
→ fractured
→ annealed
```

而不是明显的 preset 切换。

---

# 56. Phase 5 — Determinism / Seek / Export

新增：

```text
app/dynamics/deterministic.py
```

### 5.1 track stable seed

### 5.2 simulation randomness 与 render randomness 分离

### 5.3 frame/event keyed deterministic noise

### 5.4 seek rebuild

### 5.5 parallel export seam test

### 5.6 固定 simulation timestep

**完成标准：**

同一歌曲、同一时间：

```text
实时
串行导出
并行导出
Seek 后
```

宏观世界状态一致。

---

# 57. Phase 6 — Chladni / richer physics-inspired geometry

只有到此时才加入：

- nodal resonance / Chladni-like curves
- defect patterns
- richer vortex texture
- denser field visualization

并且它们必须服务于统一 MaterialState。

不要重新变成 preset library。

---

# 58. Phase 7 — 真正 GPU Renderer

最后再做：

- GLSL field sampling
- GPU particles
- dense flow
- phase-field texture
- bloom/composite

CPU 保留 fallback。

MaterialState 和 Context 完全共用。

---

# 59. 推荐的 commit 粒度

不要让 Agent 一次改几十个文件后才测试。

建议：

```text
commit 1  fix feature scaling
commit 2  fix beat fallback + confidence
commit 3  fix/reset field lifecycle
commit 4  causal L3 windows
commit 5  VisualContext
commit 6  MaterialStateEngine
commit 7  precompiled trajectory
commit 8  deterministic tests
commit 9  analytic PES
commit 10 particle phase coupling
commit 11 geometry phase coupling
commit 12 seek/export determinism
commit 13 optional nodal geometry
```

每一步保持程序可运行。

---

# 60. 不建议本轮做的事情

为了防止 vibe coding 再次失控，明确禁止以下“看起来很厉害但会拖垮项目”的扩张：

- 不做完整 Navier–Stokes solver。
- 不做真正 3D CFD。
- 不做真实等离子体 PIC。
- 不做真实 DFT/PES 概念模拟。
- 不做 Skyrmion，除非有真正向量场拓扑。
- 不做机器学习 genre classifier。
- 不引入 PyTorch。
- 不引入新的大型 GUI framework。
- 不因为 physics 名字好听而新增 20 个状态变量。
- 不在 CPU 模式追求百万粒子。
- 不为了 GPU 而重写整个播放器。
- 不要求 CPU/GPU pixel-perfect。
- 不删除现有 VisualDNA/Theme 体系，只把它从“主宰结构”降级为 prior。
- 不把 `crystal/fluid/plasma` 做成三个互斥 renderer class。

---

# 61. 目前源码中还值得顺手记录的工程债

这些不一定全部属于 V2 blocker，但 Agent 修改附近代码时可以顺手处理。

---

## 61.1 `app.visual.__init__` eager import Qt renderer

导致纯 physics 单测也依赖 PySide6。

建议 pure dynamics 移出 `app.visual`。

---

## 61.2 `FeatureFrame.get_frame_dict_at_time()` 类型注解不完全准确

返回 dict 中包含 `np.ndarray` chroma，而不是全部 `float`。

---

## 61.3 `compute_event_density()` 每个窗口扫描所有 event

当前歌曲长度下问题不大。

若未来长音频，可用 `searchsorted` 优化。

---

## 61.4 section extraction 中有一些中间量未实际使用

当前：

```text
mel spectrogram
S_log
mfcc
```

随后又单独计算 `mfcc_coarse`。

可检查并删除无用计算，减少长歌曲分析开销。

---

## 61.5 recurrence matrix 对超长音频是 O(T²)

对普通 3~5 分钟音乐尚可。

若支持 1h mix / podcast，需要 downsample 或设置上限。

---

## 61.6 Scene / constants 的 max particle 定义不一致

constants：

```text
MAX_PARTICLES = 500
```

Scene：

```text
ParticleSystem(max_particles=1600)
```

建议单一来源。

---

## 61.7 `motion_性格`

Python 可以运行，但长期维护建议改成：

```text
motion_character
```

保留兼容 alias 即可。

---

## 61.8 `type` 作为 ParticleSystem.emit 参数名

会遮蔽 Python builtin `type`。

建议以后改成：

```text
particle_type
```

不是 blocker。

---

## 61.9 QThread.terminate()

当前切歌时可能直接 terminate analysis thread。

这是 Qt 中偏危险的强终止方式。

不属于本次视觉重构核心，但后续可以改 cooperative cancellation。

---

# 62. README / 技术文档的物理术语建议

推荐的措辞：

### 可以放心使用

```text
physics-inspired
artificial material
phase-space trajectory
order parameter
excitation
defect density
hysteresis-inspired dynamics
potential field
conservative force
curl/vortex field
nodal resonance geometry
```

### 使用时加限定词

```text
effective temperature-inspired
phase-transition-inspired
crystal-like
plasma-like
```

### 暂时不要使用

```text
Skyrmion
bandgap emission
laser line emission
true blackbody radiation
thermodynamically rigorous
real hydrodynamics
real plasma simulation
```

除非未来真的实现对应数学定义。

---

# 63. 一个推荐的最终核心 API

理想情况下，Renderer 每帧只需要看到：

```python
context = visual_context.at(t)
material = material_trajectory.at(t)

field.update(
    context=context,
    material=material,
)

scene.update_simulation(
    time=t,
    context=context,
    material=material,
    field=field,
)

renderer.draw(
    scene=scene,
    material=material,
)
```

而不是：

```python
renderer(
    rms,
    bass,
    high,
    centroid,
    chaos,
    global_energy,
    beat,
    ...
)
```

---

# 64. 推荐的 Renderer 思维模型

以后遇到一个新视觉需求时，不要问：

> “这个特效应该绑定哪个音频 feature？”

应该问：

> “这个现象属于人工物质的哪个状态变量？”

例如：

### “线条断裂”

不要：

```text
onset > 0.8 -> break line
```

而是：

```text
onset -> defect creation
defect_density -> fragmentation
```

### “旋涡变强”

不要：

```text
bass > 0.7 -> vortex
```

而是：

```text
beat density / mobility -> fluid state
fluid weight -> curl strength
```

### “规则晶格出现”

不要：

```text
quiet -> draw_chladni()
```

而是：

```text
order ↑
defect ↓
tonal confidence ↑
    ↓
symmetry / nodal coherence ↑
```

这一原则是防止 V2 再次同质化的核心。

---

# 65. 最终验收标准

只有满足以下条件，才算 V2 的核心重构成功。

## 必须满足

### A. 数据正确

- centroid/rolloff 无双重归一化；
- spectral contrast 有明确尺度；
- no-beat 不再伪造 120 BPM；
- global spectral balance 不再来自独立归一化 band 的假比例；
- L3 无无意未来泄漏/尾部归零。

### B. 物态真正有历史

- 同一当前输入、不同过去，可在合理时间内得到不同 state；
- defect 可以积累与缓慢恢复；
- silence 不变成强流体。

### C. Phase 真正进入画面

不仅 HUD 显示 phase。

必须改变：

- geometry
- particle force
- coherence
- fragmentation
- circulation

### D. 不再是三 preset

中间 phase weights 能产生大量连续形态。

### E. Seek 正确

Seek 后 material state 与对应时间一致。

### F. 导出一致

串行/并行不出现明显 segment seam。

### G. FPS 独立

Material trajectory 不受 30/60/120 FPS 改变。

### H. 性能可接受

PES 不再靠每粒子 × 3 次 potential × 12 chroma 的 numerical finite difference。

---

# 66. 视觉层最终应呈现的体验

理想情况下，同一首歌可能出现：

```text
Dormant ordered field
    ↓
Crystalline locking
    ↓
Local defects from transients
    ↓
Defect accumulation
    ↓
Softening / mobile fluid
    ↓
Strong vortex transport
    ↓
High-excitation fragmented state
    ↓
Cooling
    ↓
Nucleation
    ↓
Recrystallization
```

这些不是固定时间表。

音乐只是改变驱动力。

---

# 67. 项目最终的“灵魂句”

如果实现达到本文件目标，Stormy-Pulse 最有辨识度的描述不应是：

> A beautiful audio-reactive music visualizer.

也不应只是：

> A physics-themed music visualizer.

而应接近：

> **Stormy-Pulse treats music as a perturbation acting on a continuously evolving artificial material. Visual structures emerge from the material's trajectory through phase space rather than from direct one-to-one mappings between audio features and effects.**

这句话对应的必须是真实代码架构，而不是 README 文案。

---

# 68. 最后给开发 Agent 的一句执行摘要

**先把当前音频数据的尺度、beat fallback、L3 时间语义、reset/seek、随机确定性修好；然后建立 `VisualContext → MaterialStateTrajectory → Field → Geometry/Particles` 这一条主干。**

PhaseEngine 不要继续当三分类器，而要变成带 `defect_density` 等慢变量的有记忆动力学系统；MaterialState 建议预编译以彻底解决 FPS、Seek 和并行导出问题。PES 改成 tonal-confidence-gated、circle-of-fifths/Fourier、解析梯度的场，并让 Crystal/Fluid/Plasma weights 控制 conservative/curl/stochastic 三类力的比例。Renderer 通过连续 GeometryControl morph 同一个世界，而不是切换三套 preset。

**在以上主干打通之前，不要优先开发 Chladni、Skyrmion、Navier–Stokes、Plasma Shader 等新名词/新特效。**

真正解决同质化的不是“效果数量”，而是：

\[
\boxed{
\text{同一瞬时声音}
+
\text{不同历史}
\Rightarrow
\text{不同世界状态}
\Rightarrow
\text{不同画面}
}
\]

这应该成为 Stormy-Pulse V2 所有后续实现决策的最高原则。
