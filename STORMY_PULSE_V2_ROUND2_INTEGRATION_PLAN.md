# Stormy-Pulse V2 Round 2：主链路集成、语义修复与验收计划

> **文档性质**：第二轮开发执行文档 / 集成验收清单  
> **审计基线**：GitHub `main` 分支，最新审计提交 `a94b14f`（2026-08-26）  
> **前置文档**：`STORMY_PULSE_V2_IMPLEMENTATION_BLUEPRINT.md`  
> **本轮目标**：禁止继续“横向新增架构”；把已经实现的 `app/dynamics/` 真正接入 Stormy-Pulse 的播放器、Scene、粒子、Renderer、Seek 和视频导出主链路，并修复第二轮审计发现的语义与测试漏洞。  
> **核心验收口径**：不能再以“类已经存在”“单元测试能 import”“README 写了 implemented”作为完成标准。只有**真实运行主链路已经使用新系统**，才算完成。

---

# 0. 给开发 Agent 的最高优先级指令

本轮不要继续设计新的 physics concept，不要再新增一套平行系统。

当前仓库已经同时存在：

```text
旧运行主链：
FeatureFrame
    ↓
app.visual.PhaseEngine
    ↓
app.visual.PESField
    ↓
Scene
    ↓
ParticleSystem / RingLayer
    ↓
VisualizerRenderer

以及：

新 V2 原型：
app.dynamics.TrackCalibration
app.dynamics.VisualContextBuilder
app.dynamics.MaterialStateEngine
app.dynamics.MaterialTrajectoryCompiler
app.dynamics.AnalyticalPESField
app.dynamics.GeometryControl
app.dynamics.deterministic
```

**本轮唯一核心任务：把第二套真正变成第一套的主干。**

禁止发生：

```text
继续新增 DynamicsClass3
继续新增 FancyPhysicsEngine
继续新增 ChladniRenderer
继续新增 PlasmaShader
继续写“Implemented”
```

但旧播放器仍完全走旧系统。

---

# 1. 本轮完成定义（Definition of Done）

只有同时满足以下条件，才能声称：

> “Stormy-Pulse V2 dynamics 已完成主链路集成。”

## 1.1 主播放器

正常加载一首歌后，必须真实创建并使用：

```text
VisualContextBuilder
MaterialTrajectoryCompiler
MaterialStateSequence / MaterialTrajectory
AnalyticalPESField
GeometryControl
```

旧 `app.visual.PhaseEngine` 与旧 `app.visual.PESField` 不得再是默认主运行路径。

---

## 1.2 Scene

`Scene.update()` 的宏观物态不得再自行在线计算：

```python
old_phase_engine.update(...)
```

而应该根据当前绝对时间查询：

```python
material_state = material_trajectory.at(time)
context = visual_context.at(time)
```

Scene 只负责：

- 短时 visual simulation；
- particles；
- effects；
- geometry envelopes；

不再负责重新发明宏观 phase trajectory。

---

## 1.3 Renderer

Renderer 必须真实读取：

```text
GeometryControl
MaterialState
```

至少以下字段必须肉眼可见地改变画面：

```text
symmetry
coherence
angular_lock
circulation
fragmentation
defect_strength
roughness
```

仅仅 HUD 显示：

```text
Crystal 0.63
Fluid 0.31
Plasma 0.06
```

不算集成。

---

## 1.4 ParticleSystem

粒子至少必须区分：

```text
conservative potential force
curl / circulation force
plasma stochastic / defect scattering force
```

并由 continuous phase weights 混合。

---

## 1.5 Seek

从 180 s seek 回 40 s 后：

```text
MaterialState(40s)
```

必须是这首歌 40 s 的预编译状态，而不是 180 s 的残留。

---

## 1.6 Parallel export

各 segment worker 必须读取同一个宏观 Material trajectory。

宏观 phase 不允许依赖 5~8 s preroll “猜回来”。

---

## 1.7 Determinism

同一首歌、同一绝对时间：

```text
实时播放
串行导出
并行导出
Seek 重建后
```

必须获得一致的：

```text
VisualContext
MaterialState
GeometryControl
Field coefficients
```

---

# 2. 第二轮源码审计结果：已经完成的部分

以下是 **[源码现状]**，不要重复实现。

---

## 2.1 `app/dynamics/` 已经建立

当前已经存在核心纯数学模块：

```text
app/dynamics/
    calibration.py
    context.py
    material.py
    trajectory.py
    field.py
    deterministic.py
```

这是正确的依赖方向。

本轮应继续保持：

```text
analysis -> dynamics -> visual
```

不要让：

```text
dynamics -> Qt
dynamics -> VisualizerRenderer
```

---

## 2.2 Material state 已具有真正的慢变量

已经加入：

```text
order
excitation
mobility
defect_density
activity
w_crystalline
w_hydrodynamic
w_plasma
```

`defect_density` 的 creation/healing 已经使模型具备比旧 PhaseEngine 更真实的 path dependence。

本轮不要再重新设计第四套 phase model。

先把它接通。

---

## 2.3 Material trajectory compiler 已经存在

已经有固定频率从头积分 MaterialState 的逻辑。

这是解决：

- Seek
- FPS independence
- parallel export
- long memory
- CPU/GPU semantic parity

的正确核心。

本轮必须把它变成真正产品路径。

---

## 2.4 Analytical PES 原型已经存在

已经采用：

- circle-of-fifths pitch mapping；
- chroma Fourier compression；
- analytical gradient 思路。

这条路线正确。

本轮重点：

1. 修语义问题；
2. 加真正测试；
3. 接 ParticleSystem；
4. 补 plasma force。

不要另起炉灶写 `PESFieldV3.py`。

---

## 2.5 以下旧 P0 已部分修复

已经看到：

- centroid/rolloff 二次归一化被修；
- fake 120 BPM beat fallback 已删除；
- `Scene.reset()` 已开始重置旧 phase/PES；
- 旧 PhaseEngine 已加 silence/dormant 处理；
- 旧 PES 已从 global energy 改为更局部的 drive。

这些修复保留，不要回退。

---

# 3. 第二轮审计发现的核心问题

以下是本轮必须解决的问题。

---

# 4. 问题 A：新 V2 模块目前没有接管真实主链路

## [源码现状]

当前 `Scene` 仍从：

```text
app.visual.phase_engine
app.visual.pes_field
```

导入旧系统。

新：

```text
app.dynamics.material
app.dynamics.trajectory
app.dynamics.field
```

没有成为默认 runtime dependency。

---

## [后果]

即使：

```text
MaterialStateEngine
AnalyticalPESField
GeometryControl
MaterialTrajectoryCompiler
```

全部单测通过，

用户运行程序看到的仍然基本是旧系统。

---

## [本轮要求]

必须完成主链迁移。

不要通过：

```python
USE_V2_EXPERIMENTAL = False
```

然后默认继续旧系统来“完成”。

如果确实需要短期 fallback，可保留：

```text
legacy mode
```

但默认模式必须是 V2。

---

# 5. 问题 B：`VisualContext` 的大量字段目前只是 placeholder

## [源码现状]

当前存在近似：

```python
energy_slow = energy_fast * 0.8
energy_trend = 0.0
transient_density = onset_norm * 0.8
beat_density = beat_impulse * beat_conf
novelty = 0.0
boundary_impulse = 0.0
climax_prior = globals.energy
section_progress = time / duration
```

这些变量名看起来已经连接 L3/L4，实际上没有。

---

## [本轮要求]

禁止保留上述 placeholder 后声称：

> “L3/L4 integrated.”

必须真实读取：

```text
FeatureCache.window_stats
FeatureCache.sections
FeatureCache.climax_candidates
FeatureCache.beat events
FeatureCache.onset events
```

---

# 6. 问题 C：TrackCalibration 的 RMS reference 坐标系错误

这是本轮第一优先级 bug。

---

## 6.1 当前问题

Calibration 统计时使用：

\[
L(t)=20\log_{10}(RMS(t)/RMS_{\max})
\]

但实际 `normalize_rms_db(raw_rms)` 默认又使用：

\[
20\log_{10}(RMS(t)/1.0)
\]

两个 dB 参考不同。

---

## 6.2 例子

假设：

```text
track max RMS = 0.2
current RMS   = 0.1
```

Calibration 坐标：

```text
-6.02 dB relative to track max
```

运行 normalize 坐标：

```text
-20 dBFS-like
```

差：

```text
≈14 dB
```

可能导致：

```text
energy_fast 被严重压低
activity 被低估
大量时间误判 dormant
```

---

## 6.3 修复

`TrackCalibration` 必须保存：

```python
rms_reference: float
```

例如：

```python
@dataclass(frozen=True)
class TrackCalibration:
    rms_reference: float
    rms_db_p10: float
    rms_db_p95: float
    flux_p95: float
    onset_p95: float
    ...
```

`compute()`：

```python
rms_reference = max(np.max(rms_arr), EPS)
```

`normalize_rms_db()`：

```python
db = 20 * log10((raw_rms + EPS) / self.rms_reference)
```

统计和调用使用完全同一个 reference。

---

## 6.4 测试

禁止只用 constant RMS。

测试数据：

```python
rms = np.linspace(0.02, 0.20, 1000)
```

至少验证：

```text
normalize(0.02) < normalize(0.10) < normalize(0.20)
normalize(0.20) ≈ 1
```

并验证整体 percentile mapping。

---

# 7. 问题 D：Spectral contrast 仍然使用错误尺度

## [源码现状]

原始 librosa spectral contrast 仍直接进入：

```text
global_contrast
VisualDNA branch
line_thickness
theme saturation
```

而这些地方按 `[0,1]` 使用。

---

## [本轮修复]

### 7.1 保留原始值

明确命名：

```text
spectral_contrast_raw
```

不要污染其统计意义。

### 7.2 新增视觉归一化量

例如：

```text
spectral_contrast_norm ∈ [0,1]
```

Calibration 先在真实歌曲上统计合理范围。

不要拍脑袋：

```python
contrast / 100
```

除非数据审计支持。

---

## 7.3 TrackCalibration 必须真正使用 contrast calibration

如果类中已有：

```text
contrast_low
contrast_high
```

则必须：

- 在 `compute()` 中传入真实 contrast 序列；
- 真正计算；
- `VisualContextBuilder` 真正调用；
- 旧 VisualDNA 若继续依赖 contrast，也改用 normalized variant。

---

## 7.4 测试

构造：

```text
tonal narrowband
mixed harmonic
broadband noise
```

只要求：

- 输出有限；
- 输出 `[0,1]`；
- 不全部饱和；
- 至少存在明显可区分范围。

---

# 8. 问题 E：Band ratio 仍不是真正的跨频段能量比例

## [源码现状]

当前每个 band 先各自：

```python
band /= band.max()
```

然后再比较各 band mean。

这样计算：

```text
bass_ratio / mid_ratio / high_ratio
```

并不代表真实光谱能量比例。

---

## [本轮设计]

必须同时保留两套概念：

### 8.1 `band_drive`

用于动画。

每个 band 可以各自 track-relative normalize。

```text
bass_drive
low_mid_drive
mid_drive
high_mid_drive
presence_drive
brilliance_drive
```

### 8.2 `band_share`

从同一原始功率尺度计算：

\[
share_i(t)=
\frac{P_i(t)}
{\sum_j P_j(t)+\epsilon}
\]

全曲统计：

```text
global_bass_share
global_mid_share
global_high_share
```

才能用于：

- VisualDNA prior；
- spectral warmth；
- global style fingerprint。

---

## 8.3 不要破坏旧 cache 时的迁移方法

如果缓存 schema 改变：

```text
AUDIO_CACHE_VERSION bump
```

必要时第一次重新分析。

不要在旧字段上偷偷改变语义而不 bump cache。

---

# 9. 问题 F：L3 时间窗口仍是 forward-looking

---

## 9.1 当前

窗口：

```python
start = i * hop
end = start + window
```

所以：

```text
t=20s, window=8s
```

描述：

```text
20~28s
```

---

## 9.2 本轮默认改为 trailing causal

定义：

```text
2s: [t-2, t]
4s: [t-4, t]
8s: [t-8, t]
```

歌曲开头：

```text
[0,t]
```

不补未来。

---

## 9.3 为什么即使是离线播放器也建议 causal

虽然整首歌已经预分析，可以合法看未来，但：

- 副歌尚未进入时画面提前爆发会错位；
- phase transition 会提前；
- 用户感知会认为“视觉抢拍”。

未来如果想做 look-ahead：

```text
anticipation feature
```

应作为明确独立功能，而不是窗口定义无意造成。

---

# 10. 问题 G：2/4/8s stats 长度不同但共用时间轴

---

## [本轮要求]

所有 window stats 必须覆盖统一：

```text
t = 0 ... duration
```

建议统一按 1 Hz：

```text
times = 0,1,2,...floor(duration)
```

每个时间点都计算 trailing window。

因此：

```text
len(stats_2s)
=
len(stats_4s)
=
len(stats_8s)
=
len(times)
```

---

# 11. 问题 H：L3 查询使用整数秒阶梯

当前类似：

```python
idx = int(time)
```

---

## [修复]

实现线性插值：

```python
value(t) =
(1-u)*value[i]
+
u*value[i+1]
```

对于 density / trend / mean 都可以插值。

如果某些值天然是离散标签，单独处理，不要统一强行插值。

---

# 12. 问题 I：`section_progress` 当前其实是“全曲进度”

这属于语义命名 bug。

---

## [本轮修复]

真实：

```text
section_progress
```

应为：

\[
\frac{t-t_\mathrm{section,start}}
{t_\mathrm{section,end}-t_\mathrm{section,start}}
\]

裁剪 `[0,1]`。

另外提供：

```text
track_progress
```

单独表示：

\[
t/T_\mathrm{song}
\]

不要再混用。

---

# 13. 问题 J：L4 不能伪装成可靠 Chorus/Verse 识别

当前 section 本质是通用 segment。

所以本轮只使用：

```text
section_id
section_progress
boundary_impulse
novelty
section_energy_relative
climax_prior
```

不要写：

```python
if section_type == "chorus":
```

除非以后真的有可靠结构分类器。

---

# 14. VisualContextBuilder 本轮具体实现

---

## 14.1 构造函数建议

```python
class VisualContextBuilder:
    def __init__(
        self,
        feature_cache: FeatureCache,
        calibration: TrackCalibration,
    ):
        ...
```

不要只给一个 `FrameFeatureSequence`。

因为它需要：

```text
L1
L2 events
L3 windows
L4 sections
L5 globals
```

---

## 14.2 每时刻查询

```python
def at(self, time: float) -> VisualContext:
```

建议真实字段来源：

```text
activity
    <- calibrated RMS + signal presence

energy_fast
    <- calibrated current RMS / short envelope

energy_slow
    <- L3 4s/8s energy mean

energy_trend
    <- L3 energy trend

bass_drive/mid_drive/high_drive
    <- L1

spectral_brightness
    <- centroid_norm + high/presence drive

spectral_noise
    <- flatness + contrast_norm complement

spectral_tilt
    <- real raw band share / brightness

onset
    <- L1 onset strength calibrated

flux
    <- L1 flux calibrated

beat_impulse
    <- distance to nearest beat + beat strength

beat_confidence
    <- L5 / analysis

transient_density
    <- L3 event density

beat_density
    <- L3 beat event density

harmonic_ratio
    <- harmonic/(harmonic+percussive+eps)

tonal_confidence
    <- chroma entropy + harmonic ratio + activity

chroma
    <- smoothed chroma

novelty
    <- L4

boundary_impulse
    <- section boundary distance

climax_prior
    <- L4 climax candidate / section-relative energy

section_progress
    <- actual current section progress
```

---

# 15. Beat impulse 不要只是一个瞬时 bool

建议：

\[
d = |t-t_\mathrm{nearestbeat}|
\]

在窗口内：

\[
beat\_impulse
=
strength
\times
e^{-d/\tau}
\]

或三角核。

这样 60Hz Material trajectory 能平滑感知 beat，不依赖恰好 frame 命中某个毫秒。

---

# 16. Boundary impulse 同理

段落边界：

```text
boundary_time
```

不要只有：

```text
t == boundary
```

使用短暂 kernel：

```text
±100~300 ms
```

或因果 decay：

```text
boundary 后快速衰减
```

Material model 可以利用它暂时增大 susceptibility。

---

# 17. Chroma smoothing 本轮应完成

当前 AnalyticalPES 已经值得使用，但 chroma 不能直接逐帧抖动。

---

## 建议

在 VisualContext 或 trajectory compile 中做时间平滑：

```text
tau ≈ 100~300 ms
```

不要在 Renderer 做。

这样：

```text
同一个 Material trajectory
```

在 CPU/GPU 上获得同样 field topology。

---

# 18. MaterialTrajectory 的真正接入位置

推荐在**音频分析完成以后**生成。

伪流程：

```python
cache = extractor.extract(...)

calibration = TrackCalibration.compute(cache)

context_builder = VisualContextBuilder(
    feature_cache=cache,
    calibration=calibration,
)

trajectory = MaterialTrajectoryCompiler(
    context_builder=context_builder,
    simulation_hz=60.0,
).compile()
```

然后把：

```text
feature_cache
context_builder
trajectory
```

一起交给 renderer/scene。

---

# 19. 不要在 UI thread 做很慢的额外 compile

Material trajectory 应该只是：

```text
几十维 scalar × 60Hz × 几分钟
```

理论上非常轻。

但仍需：

- 实际 benchmark；
- 最好在 analysis worker 完成阶段一起生成；
- UI 显示“Preparing dynamics...”时不要卡界面。

如果 compile 已经 <100~300ms，无需复杂异步框架。

不要为了一个轻量任务重新造线程池。

---

# 20. Dynamics cache 策略

本轮建议暂时：

```text
audio feature cache：持久化
material trajectory：加载后快速重新 compile
```

理由：

Phase 参数仍会频繁 vibe。

不要一改：

```text
heal_rate
prototype
geometry mapping
```

就让用户重新 HPSS/CQT。

---

## 20.1 版本

至少定义：

```python
AUDIO_CACHE_VERSION
DYNAMICS_VERSION
```

即使 trajectory 暂时不落盘，也记录：

```text
DYNAMICS_VERSION
```

方便 debug。

---

# 21. Scene API 重构

目标是让 Scene 不再承担宏观材料演化。

推荐：

```python
scene.update(
    time=time,
    dt=dt,
    context=context,
    material=material,
    geometry=geometry,
)
```

而不是：

```python
scene.update(feature_frame, ...)
```

然后 Scene 内部再：

```text
重新算 brightness
重新算 phase
重新算 field
```

---

# 22. 兼容迁移：FeatureFrame 不需要立刻删除

可以短期保留：

```python
frame = cache.get_frame_at_time(t)
```

用于某些还没迁移的旧 effect。

但新增逻辑禁止继续从 FeatureFrame 直接连 Renderer。

迁移完成后再逐步收口。

---

# 23. 旧 `app.visual.PhaseEngine` 的处理方式

本轮完成后：

```text
默认路径不得使用
```

可以：

### 方案 A

删除。

### 方案 B

移动到：

```text
app/visual/legacy_phase_engine.py
```

更推荐 B 一段时间，方便对比。

在文件头标：

```python
"""Legacy V1 online phase filter.
Not used by the default V2 runtime.
"""
```

避免未来 Agent 又误接回去。

---

# 24. 旧 `app.visual.PESField` 同理

迁移至 legacy 或删除默认引用。

新的运行场必须来自：

```text
app.dynamics.field.AnalyticalPESField
```

---

# 25. AnalyticalPES 当前的关键 bug：Plasma weight 读取了但没使用

这是本轮必须修。

---

## 25.1 当前逻辑问题

如果：

```text
w_crystal
w_fluid
w_plasma
```

已计算，

但 force 只有：

```text
potential
curl
```

则 Plasma 没有独立运动机制。

---

# 26. 还存在更深的问题：tonal confidence 不应控制整个场

如果：

```python
field_gain *= tonal_confidence
```

然后：

```text
potential
curl
```

都乘同一个 gain，

那么：

```text
noisy / percussive / plasma-like
```

的段落恰恰会使：

```text
tonal_confidence ↓
```

最后整个 field 消失。

这与目标相反。

---

# 27. 正确拆分 Field components

定义：

\[
\mathbf F =
\mathbf F_c
+
\mathbf F_f
+
\mathbf F_p
\]

---

## 27.1 Crystal conservative field

\[
\mathbf F_c
=
w_c
\,
g_c
\,
\mathbf F_\mathrm{potential}
\]

其中：

```text
g_c
~ tonal_confidence
~ order
~ activity
```

---

## 27.2 Fluid curl field

\[
\mathbf F_f
=
w_f
\,
g_f
\,
\mathbf F_\mathrm{curl}
\]

其中：

```text
g_f
~ mobility
~ activity
~ beat_density / groove
```

**不要乘 tonal_confidence 作为总 gate。**

---

## 27.3 Plasma stochastic / scattering

\[
\mathbf F_p
=
w_p
\,
g_p
\,
\mathbf F_\mathrm{noise}
\]

其中：

```text
g_p
~ excitation
~ defect_density
~ activity
```

---

# 28. Plasma noise 必须 deterministic

不要：

```python
random.uniform(-1,1)
```

在每 particle 每 frame 直接抽。

使用：

```text
track_seed
simulation_tick
particle_id
stream_id
```

派生 deterministic noise。

---

## 28.1 可选方案：continuous hash noise

不要让粒子每 1/60 秒随机方向完全白噪抖动。

可以：

- 每 N tick 更新目标 noise；
- 中间插值；
- 或使用 deterministic smooth noise。

这样 Plasma 看起来是“受扰动的运动”，不是电视雪花。

---

# 29. Analytical gradient 测试现在不合格

当前测试虽然计算：

```text
finite-difference reference
```

但没有真正 assert analytic 与 numerical 的误差。

---

## 必须改成

随机采样若干点：

```python
fx_a, fy_a = analytic(...)
fx_n, fy_n = finite_difference_reference(...)
```

比较：

```python
np.testing.assert_allclose(
    [fx_a, fy_a],
    [fx_n, fy_n],
    rtol=...,
    atol=...
)
```

---

## 注意

靠近：

```text
r=0
```

的点可单独测试，因为 polar conversion 数值更敏感。

不要用一个统一极严容差导致假失败。

---

# 30. Field 测试至少增加以下五项

1. analytical gradient reference；
2. zero activity -> bounded near-zero force；
3. zero tonal confidence -> crystal potential suppression；
4. fluid state -> curl 非零；
5. plasma state -> deterministic stochastic term 非零。

---

# 31. ParticleSystem 本轮必须真正接 MaterialState

建议：

```python
particles.update(
    dt,
    material=material,
    field=field,
    simulation_tick=tick,
    track_seed=seed,
)
```

---

# 32. 不要让粒子只收到统一 force

不同粒子类型可以有轻度响应差异：

```text
ambient dust:
    field coupling low

orbiting/core particles:
    potential coupling high

burst particles:
    defect/scatter sensitivity high
```

但不要第一轮就引入 20 种 particle species。

---

# 33. Particle drag 应由 material 控制

例如：

```text
Crystal:
    drag ↑
    mobility ↓

Fluid:
    drag medium
    circulation ↑

Plasma:
    drag ↓
    stochastic ↑
```

最好使用连续：

\[
drag =
w_c d_c
+
w_f d_f
+
w_p d_p
\]

不要：

```python
if phase_name == ...
```

---

# 34. Renderer 本轮真正要做的事

这是反同质化是否成功的核心。

---

# 35. GeometryControl 必须从“漂亮 dataclass”变成 Renderer 输入

Renderer API 推荐：

```python
draw_scene(
    painter,
    scene,
    material,
    geometry,
    ...
)
```

至少以下现有层要读取 geometry：

- main ring / shell；
- harmonic shell；
- generative structure；
- line continuity；
- deformation；
- optional background field。

---

# 36. 第一轮 geometry morph 不要过度复杂

本轮只需要证明：

> 相同旧 VisualDNA，在不同 MaterialState 下可以长得明显不一样。

---

## 36.1 Symmetry

作用：

- angular mode integer locking；
- segment placement regularity；
- mirrored / rotational coherence。

---

## 36.2 Coherence

作用：

- 相邻 curve phase 连续度；
- line smoothness；
- geometry persistence。

---

## 36.3 Angular lock

作用：

- 是否锁定稳定 nodal directions；
- Chroma/Fourier phase 是否严格约束 shell。

---

## 36.4 Circulation

作用：

- angular warp；
- curve advection；
- swirl deformation。

---

## 36.5 Fragmentation

作用：

- broken segment probability；
- arc gap；
- local split。

---

## 36.6 Defect strength

作用：

- 局部 phase slip；
- radial displacement；
- symmetry-breaking perturbation。

---

## 36.7 Roughness

作用：

- fine-scale perturbation；
- plasma surface instability。

---

# 37. `broken_segments` 应真正被 defect dynamics 驱动

现有 RingLayer 若已经有：

```text
broken_segments
```

不要继续空置。

---

## 37.1 关键：broken segment 不能每帧随机重抽

否则缺陷没有“物理寿命”。

建议每个 defect 有：

```python
@dataclass
class VisualDefect:
    id: int
    angle: float
    width: float
    strength: float
    birth_tick: int
    heal_tau: float
```

但第一版可以更简洁：

```text
deterministic defect mask
```

由：

```text
track_seed + material defect_density + time chunk
```

生成，并平滑演化。

---

# 38. 不要让 GeometryControl 直接等于 audio feature

错误：

```python
fragmentation = onset
```

正确：

```text
onset
    ↓
MaterialState.defect_density
    ↓
GeometryControl.fragmentation
```

这样才有历史。

---

# 39. `structure_type` 本轮必须降级

当前：

```text
reactor / vortex / organic / pulse
```

仍可以保留。

但是：

```text
structure_type
```

不得继续：

> 决定整首歌唯一主体 topology。

---

## 39.1 短期方案

它只修改 GeometryControl 的 baseline：

```python
if prior == "vortex":
    circulation_prior += small_amount

if prior == "reactor":
    radial_order_prior += small_amount
```

量级不能大到覆盖 phase dynamics。

---

# 40. VisualDNA 应变成“先天材质”，不是“歌曲模板”

这可以保留旧项目特色，同时解决同质化。

解释：

```text
VisualDNA:
    这块人工材料天生偏什么风格

MaterialState:
    这块材料此刻变成了什么状态
```

---

# 41. Deterministic RNG 当前只是 utility，没有接产品

本轮必须真正替换关键全局 random。

---

# 42. 随机调用分类

先 grep 全项目：

```text
random.
np.random
```

逐个标记：

### A. simulation state randomness

必须 deterministic。

例如：

- particle emission；
- particle initial angle；
- speed；
- plasma kicks；
- defect creation。

### B. render-only decorative randomness

必须按 frame/index deterministic。

例如：

- tiny background spikes；
- grain；
- decoration jitter。

### C. offline nonvisual randomness

若存在，可独立处理。

---

# 43. 不要使用一个共享 stateful RNG 解决所有问题

因为：

```text
CPU path 多 draw 一次
```

就可能多消耗一个 random number，

然后整个未来 particle world 分叉。

---

## 推荐

```python
deterministic_float(
    track_seed,
    stream_id,
    tick,
    object_id,
    component_id,
)
```

---

# 44. Particle ID 必须稳定

如果 deterministic noise 使用 particle id，

Particle 需要：

```text
stable id
```

不要使用：

```text
list index
```

因为删除一个粒子会让后面所有粒子 index 改变。

Scene 维护：

```python
next_particle_id
```

递增即可。

---

# 45. 时间离散：Material 与 Particle 分开

---

## Material

预编译：

```text
60 Hz
```

或固定 simulation Hz。

---

## Particle/visual state

实时播放可以：

```text
fixed-step accumulator
```

例如：

```python
SIM_DT = 1/60
```

Renderer FPS 独立。

---

# 46. Fixed-step accumulator 示例

概念：

```python
accumulator += real_dt

while accumulator >= SIM_DT:
    simulate_one_tick(SIM_DT)
    accumulator -= SIM_DT
```

如果窗口卡顿很久：

```text
限制 max catch-up steps
```

避免死亡螺旋。

---

# 47. Export 必须使用绝对 frame time

例如导出：

```text
fps = 30
frame n
t = n / fps
```

宏观：

```python
material = trajectory.at(t)
context = context_builder.at(t)
```

粒子 simulation：

按固定 tick 推进。

---

# 48. Seek 本轮具体实现

当前 Seek 只是移动音频时间。

本轮至少实现：

```python
scene.seek_to(time)
```

---

## 48.1 `Scene.seek_to(t)` 做什么

1. 清空 transient effects；
2. 清空 particles；
3. 清空 camera shake；
4. 重置 short-term envelopes；
5. 查询正确 `MaterialState(t)`；
6. 从：

```text
max(0, t - PARTICLE_WARMUP)
```

固定步长快速模拟到 `t`。

---

## 48.2 Material 不需要 warmup

因为：

```text
MaterialTrajectory
```

已经从歌曲开头完整编译。

这正是预编译轨迹的意义。

---

# 49. Particle warmup 多长？

根据最大 visible particle lifetime 决定。

不要拍脑袋一直写 5 秒。

统计：

```text
max normal particle lifetime
max ring transient decay
max effect decay
```

定义：

```python
VISUAL_WARMUP_SECONDS
```

例如：

```text
6~8s
```

由现有 effect 生命周期决定。

---

# 50. Seek backward/forward 都必须走同一重建协议

不要：

```text
向后 seek 才 reset
向前 seek 继续跑
```

用户从：

```text
20s -> 150s
```

也不可能真的模拟中间 130s。

任何非连续 jump：

```text
abs(new_t - old_t) > threshold
```

都走 rebuild。

---

# 51. Parallel exporter 本轮具体改法

每个 worker 不需要从 segment 前几十秒恢复宏观 phase。

所有 worker 共享/重建同一个 deterministic：

```text
FeatureCache
VisualContextBuilder
MaterialTrajectory
```

---

## 51.1 宏观状态

任意：

```text
t
```

直接 query。

---

## 51.2 粒子状态

worker 从：

```text
segment_start - VISUAL_WARMUP_SECONDS
```

开始 simulate。

因为 particle lifetime 短。

---

## 51.3 RNG

由于使用 stateless deterministic keys，

同一 warmup 区间产生的粒子应与串行导出一致。

这样 segment seam 才真正可控。

---

# 52. 串行/并行一致测试必须加入

选择一个 10~20s synthetic 或短音频 fixture。

在：

```text
segment boundary - 1 frame
segment boundary
segment boundary + 1 frame
```

比较：

```text
MaterialState
GeometryControl
particle count
selected particle state statistics
raw image difference
```

---

# 53. 先不要要求最终编码 MP4 bit-identical

FFmpeg / 编码器线程可能造成二进制差异。

比较：

```text
pre-encoding raw frame
```

或 QImage / RGB buffer。

---

# 54. 新 Material state 的数值范围必须加 invariant test

每个 tick：

```text
finite
```

并满足：

```text
0 <= order <= 1
0 <= excitation <= 1
0 <= mobility <= 1
0 <= defect_density <= 1
0 <= activity <= 1

w_c >= 0
w_f >= 0
w_p >= 0
abs(w_c+w_f+w_p - 1) < tolerance
```

---

# 55. Hysteresis 测试需要更严格

当前已有 path-dependence 思路，但本轮增加：

```text
ordered path
high-excitation path
```

进入相同 middle context。

至少在一个合理宏观时间尺度内：

```text
defect_B > defect_A
order_B < order_A
```

并最终在长时间相同输入下允许逐渐收敛。

不要要求永久不同。

---

# 56. Material trajectory 的测试

---

## 56.1 Monotonic timestamps

```text
times strictly increasing
```

---

## 56.2 Query interpolation

随机：

```text
t between ticks
```

检查：

```text
state.at(t)
```

没有 step artifact。

phase weights 插值后要重新 normalize 或保证 sum≈1。

---

## 56.3 Boundary

```text
t < 0
t > duration
```

应 clamp。

不能 index error。

---

# 57. 30 / 60 / 120 FPS independence 的正确测试方法

Material trajectory 本身固定。

分别模拟 Renderer 查询：

```text
30fps times
60fps times
120fps times
```

在共同绝对时间点查询：

```text
MaterialState
```

必须一致。

这比把 MaterialEngine 分别用三个 dt 在线跑更符合新架构。

---

# 58. VisualContext 测试必须摆脱“constant fixture”

当前 constant RMS 容易掩盖 calibration bug。

测试 fixture 至少包括：

```text
ramp
step
pulse
silence
harmonic
noise
beat train
```

---

# 59. L3 causal test

构造：

```text
0~10s energy = low
10~20s energy = high
```

在：

```text
t=9s
```

8s causal mean 绝对不能包含 10s 以后 high energy。

这个测试非常重要。

---

# 60. L3 tail test

在歌曲最后：

```text
duration - 1s
```

请求：

```text
2s
4s
8s
```

都必须返回有效值。

不能因为较长窗口数组短而归零。

---

# 61. Section progress test

给 synthetic sections：

```text
0~10
10~30
30~50
```

检查：

```text
t=20
section_progress = 0.5
```

而不是：

```text
20/50 = 0.4
```

---

# 62. Beat failure test

无 peak 输入：

```text
beat_times = []
beat_confidence = 0
```

并验证：

```text
VisualContext.beat_impulse = 0
beat_density = 0
```

绝不能隐性重新制造 120 BPM。

---

# 63. Tonal confidence 测试

### Uniform chroma

entropy 高：

```text
tonal_confidence low
```

### One/two dominant pitch classes

entropy 低：

```text
tonal_confidence higher
```

但 activity≈0 时：

```text
tonal_confidence -> effectively suppressed
```

---

# 64. Renderer 测试：至少加入参数敏感性测试

即使不做复杂 image snapshot，也应该验证：

```text
GeometryControl.crystal-like
GeometryControl.fluid-like
GeometryControl.plasma-like
```

产生的中间 geometry params 不相同。

---

# 65. 推荐增加轻量 GeometryDescriptor 单测层

在真正 QPainter 前：

```python
descriptor = ring_layer.compute_geometry(...)
```

返回：

```text
segment angles
radii
mode amplitudes
gaps
warp
```

这样可以无 GUI 测试。

避免所有视觉逻辑只能肉眼检查。

---

# 66. 不要把所有 Geometry math 都埋在 `paint()`

目标：

```text
state -> geometry description
```

纯数学；

```text
geometry description -> QPainter
```

纯绘制。

这样未来 GPU 迁移时可以复用前半段。

---

# 67. Headless 测试依赖

继续确保：

```text
app.dynamics
```

导入时完全不需要 PySide6。

如果测试：

```python
from app.dynamics.material import ...
```

却触发 Qt import，

说明依赖方向又坏了。

---

# 68. MainWindow 的职责边界

MainWindow 只应该：

1. 接收 analysis complete；
2. 保存 cache；
3. 创建/接收 dynamics bundle；
4. 交给 visual widget；
5. 管理播放器控制。

不要在 MainWindow 里面写 phase 公式。

---

# 69. 推荐定义 `DynamicsBundle`

为了避免到处传五个对象：

```python
@dataclass
class DynamicsBundle:
    calibration: TrackCalibration
    context_builder: VisualContextBuilder
    material_trajectory: MaterialTrajectory
    track_seed: int
```

如果 field 只存少量 transient coefficient，也可以由 Scene 自己持有。

---

# 70. Renderer/Scene 接口不要继续膨胀几十个参数

错误：

```python
scene.update(
    rms,
    bass,
    mid,
    high,
    flux,
    novelty,
    order,
    defect,
    ...
)
```

正确：

```python
scene.update(
    time=t,
    dt=dt,
    context=context,
    material=material,
    geometry=geometry,
)
```

---

# 71. `GeometryControl` 应该在哪里计算？

推荐纯 dynamics/controller 层：

```text
MaterialState + global style prior
        ↓
GeometryControl
```

可以在：

```text
app/dynamics/material.py
```

或单独：

```text
app/dynamics/geometry.py
```

但本轮**不要为了整洁再拆十个文件**。

如果已有 GeometryControl 逻辑，直接完善。

---

# 72. GeometryControl 也需要平滑吗？

MaterialState 已经平滑。

所以绝大多数 geometry control：

```text
直接从 MaterialState 推导
```

即可。

不要每层：

```text
Material smoothing
Geometry smoothing
Ring smoothing
Renderer smoothing
```

叠四层低通，最终响应迟钝。

---

# 73. 需要保留的快速 transient 通道

并不是所有视觉都要经过慢 MaterialState。

这是很重要的平衡。

例如：

```text
kick/snare onset
```

可以直接触发：

- 短 flash；
- shock ring；
- spark burst。

但：

```text
宏观 topology
```

必须来自 MaterialState。

即：

```text
Audio transient -> short local event
Audio history   -> material topology
```

两层同时存在。

否则 V2 可能“物理很高级但不跟拍”。

---

# 74. 快速 event 必须被 material 调制

同一个 onset：

### Crystal

```text
产生局部 crack / phonon-like ripple
```

### Fluid

```text
产生 vortex impulse / wave
```

### Plasma

```text
产生 spray / fragmentation
```

这样 instant event 也不会重新退化成固定特效。

---

# 75. 本轮不要实现真正 Chladni

可以暂时做：

```text
nodal-like harmonic shell
```

证明 `angular_lock/symmetry` 有视觉效果。

真正 Chladni modal equation 放到下一轮。

原因：

当前最重要的仍是主链闭环，不是效果库。

---

# 76. 本轮不要新增第四个完整 Phase

`dormant` 可以作为：

```text
activity regime
```

而不是与：

```text
crystal/fluid/plasma
```

竞争 phase weight。

保持状态空间简单。

---

# 77. 本轮建议的代码迁移顺序

严格按下面顺序。

---

# Phase R2-0：修数学/分析语义

必须先完成：

1. RMS calibration reference；
2. spectral contrast normalization；
3. raw band share；
4. L3 causal window；
5. L3 equal-length timeline；
6. L3 interpolation；
7. real section_progress；
8. real L4 novelty/boundary/climax plumbing。

---

## R2-0 验收

所有这些只涉及：

```text
analysis / dynamics context
```

无需新视觉。

相关测试全部绿。

---

# Phase R2-1：完成真实 VisualContext

删除 placeholder：

```text
energy_slow = fast * 0.8
energy_trend = 0
novelty = 0
boundary = 0
```

建立：

```text
FeatureCache -> VisualContextBuilder
```

---

## R2-1 验收

用 debug script 对任意一首真实歌：

```text
每秒输出：
activity
energy_fast
energy_slow
trend
transient_density
beat_density
novelty
section_progress
```

这些值必须与歌曲明显相关。

---

# Phase R2-2：真正生成 MaterialTrajectory

分析完成时创建：

```text
DynamicsBundle
```

并交给 visual subsystem。

---

## R2-2 验收

MainWindow / Visual widget / exporter 中能找到真实调用：

```text
MaterialTrajectoryCompiler
```

不能只存在 tests。

---

# Phase R2-3：Scene 迁移到 trajectory

删除默认：

```text
old PhaseEngine.update()
```

改：

```python
material = trajectory.at(time)
context = context_builder.at(time)
```

---

## R2-3 验收

运行主程序时：

```text
old PhaseEngine
```

不再被调用。

可临时增加 debug assertion / logging 验证一次。

完成后删冗余日志。

---

# Phase R2-4：AnalyticalPES 接粒子

1. 修 component gain；
2. 补 plasma stochastic；
3. 加真正 analytical test；
4. ParticleSystem 改用新 field。

---

## R2-4 验收

旧 `visual.PESField.sample_force()` 不再是默认 particle force source。

---

# Phase R2-5：GeometryControl 接 Renderer

这是本轮视觉质变点。

---

## 最低要求

不写新 Chladni 的情况下，让三组人工 MaterialState：

```text
high crystal
high fluid
high plasma
```

在相同 VisualDNA 下得到明显不同主体结构。

---

# Phase R2-6：Deterministic RNG 接产品

替换关键：

```text
random.*
```

并引入 stable particle id。

---

# Phase R2-7：Seek

实现：

```text
scene.seek_to()
```

并让 MainWindow 调用。

---

# Phase R2-8：Parallel exporter

让 worker：

```text
query same MaterialTrajectory
```

并按 deterministic warmup 重建短寿视觉状态。

---

# Phase R2-9：Regression / cleanup

1. legacy phase/PES 标记；
2. 删除死 import；
3. 更新技术文档；
4. 不更新 README 为超出真实实现的说法。

---

# 78. 提交粒度建议

本轮不要一个 5000 行 commit。

推荐：

```text
commit 1
fix(dynamics): make RMS calibration reference-consistent

commit 2
fix(analysis): normalize spectral contrast and add raw band shares

commit 3
fix(analysis): make L3 rolling windows causal and aligned

commit 4
feat(dynamics): build VisualContext from real L3/L4 data

commit 5
feat(runtime): compile and attach MaterialTrajectory after analysis

commit 6
refactor(scene): consume precompiled V2 material state

commit 7
feat(field): integrate analytical PES and plasma stochastic force

commit 8
feat(renderer): drive geometry continuously from GeometryControl

commit 9
feat(determinism): use keyed randomness in scene and particles

commit 10
fix(seek): rebuild transient visual state from deterministic warmup

commit 11
fix(export): share V2 material trajectory across segment workers

commit 12
test(v2): add integration, seek, fps and export equivalence tests

commit 13
chore(v2): deprecate legacy phase/PES runtime
```

---

# 79. 每个 commit 的规则

每个 commit：

- 测试必须能运行；
- 程序至少能启动；
- 不允许把 broken intermediate state 留到后面几十个 commit 才修；
- 不允许一次性重写所有 Renderer。

---

# 80. 建议增加一个真实集成测试入口

例如：

```text
tests/test_v2_runtime_pipeline.py
```

不需要真正打开窗口。

构造：

```text
FeatureCache fixture
    ↓
VisualContextBuilder
    ↓
MaterialTrajectory
    ↓
AnalyticalPES
    ↓
GeometryControl
```

断言主链全部可走。

---

# 81. 必须有一个“旧类未被默认运行”测试/检查

可以用静态或轻量 mock。

例如 monkeypatch：

```python
legacy_phase.update = raise_error
```

然后跑默认 V2 scene path。

如果程序仍正常：

```text
说明旧 PhaseEngine 没被调用
```

同理旧 PES。

这可以防止以后 Agent 又偷偷接回旧系统。

---

# 82. 建议新增 V2 debug trajectory script

```text
scripts/plot_v2_trajectory.py
```

输入歌曲/缓存，输出：

- activity；
- excitation；
- order；
- defect；
- mobility；
- phase weights；
- section boundaries；
- novelty。

不要立即塞正式 UI。

---

# 83. 相空间图特别建议保留

绘制：

\[
x=order
\]

\[
y=excitation
\]

点颜色/大小：

```text
defect density
```

对比几首歌。

如果不同歌曲的轨迹仍全部挤在同一小块区域：

> 不要再画新特效，先调动力学。

---

# 84. Phase occupancy 也应作为开发指标

每首测试歌统计：

```text
mean w_crystal
mean w_fluid
mean w_plasma
```

警告条件：

```text
所有歌 90% 时间都是 Fluid
```

或：

```text
所有流行歌永远 Plasma
```

这说明 phase model 退化。

---

# 85. 防止 phase collapse

如果 prototype soft assignment 出现一个状态长期独占：

不要立刻加第四相。

先检查：

1. calibration；
2. state dynamic range；
3. prototype center；
4. softmax beta；
5. activity gate。

---

# 86. Defect 的时间尺度需要真实测试

目标不是：

```text
一打鼓 defect 0 -> 1
```

也不是：

```text
高潮结束 1 秒后完全恢复
```

建议视觉体验：

- creation：快；
- recovery：数秒到十几秒；
- 长静音可以慢慢 anneal。

具体数值根据真实歌曲调。

---

# 87. 不要让 climax_prior 主宰 plasma

climax 只是弱 prior。

错误：

```python
excitation += 0.8 * climax_prior
```

正确：

```text
climax 可以增大 susceptibility
```

但真正 excitation 仍来自局部音频。

否则所有“最高 RMS section”都会自动 plasma，重新 preset 化。

---

# 88. Global features 的定位

只应该影响：

```text
prior
palette
baseline material temperament
```

不应直接决定当前 phase。

---

# 89. Slow vs Fast 通道必须明确

推荐：

### Fast

```text
onset
flux
beat impulse
current RMS
```

### Slow

```text
L3 energy
L3 trend
density
defect
material state
```

Renderer 里不要混成一锅。

---

# 90. 性能预算：本轮避免 Python per-particle 重计算 context

每帧：

```text
VisualContext
MaterialState
Field coefficients
```

只计算/查询一次。

然后传给所有 particles。

不要每粒子：

```python
context_builder.at(t)
```

---

# 91. Analytical field 的 trig 也应按 frame 预计算

如果：

```text
Fourier coefficients
radial constants
curl strength
```

当前帧相同，

先在：

```python
field.prepare(context, material, tick)
```

计算。

Particle 只调用：

```python
field.sample_force(x,y,id)
```

---

# 92. 如果 CPU 仍慢，再优化，但不要过早 GPU

顺序：

1. analytical；
2. Fourier compression；
3. vectorize/batch；
4. coarse grid；
5. GPU。

不要跳 1~3。

---

# 93. GPU 本轮只保持兼容，不做大迁移

当前 OpenGL path 仍主要是 QPainter bridge。

只需要确保新的：

```text
MaterialState
GeometryControl
```

也能传进去。

真正 Shader 下一轮再做。

---

# 94. 测试与真实视觉验证必须同时存在

纯数学测试绿：

不代表漂亮。

肉眼漂亮：

不代表 Seek/导出正确。

两种都要。

---

# 95. 推荐真实测试曲库

不需要提交版权音乐到仓库。

开发者本地选：

```text
安静钢琴
流行人声
重摇滚/金属
电子舞曲
Ambient
复杂节奏/Jazz
低频重
稀疏 acoustic
```

---

# 96. 第一视觉验收问题

不要问：

> “酷不酷？”

先问：

### 同一首歌

- intro / verse / climax 是否结构不同？
- 转变连续吗？
- 是否有记忆？
- 高潮后是否缓慢恢复？

### 不同歌曲

- 是否仍像同一结构仅换色？
- phase trajectory 是否明显不同？

---

# 97. 第二视觉验收：相同瞬时输入，不同历史

这是 V2 灵魂。

人工 context：

```text
Path A:
ordered 20s
→ middle

Path B:
chaotic 20s
→ middle
```

进入相同 middle 时：

主体 geometry 必须仍有差异。

不仅是 HUD 数字差异。

---

# 98. 第三视觉验收：静音

静音时：

- field 不应高速旋转；
- 粒子不应莫名爆炸；
- material excitation 应衰减；
- defect 缓慢修复；
- 可留下淡淡 dormant structure。

---

# 99. 第四视觉验收：无节拍 Ambient

不能因为 beat fallback 再变成规则 120 BPM pump。

应该主要由：

```text
slow energy
tonal field
spectral drift
```

驱动。

---

# 100. 第五视觉验收：强噪声/强打击段落

即使 tonal confidence 很低：

- Fluid/Plasma 运动仍要强；
- 只有 conservative tonal PES 应减弱；
- curl/stochastic 不应一起消失。

---

# 101. 文档与命名同步

本轮代码真正完成后，再更新：

```text
PROJECT_TECHNICAL_DOC.md
README
```

---

## README 禁止写

```text
Full analytical physical simulation
Real plasma dynamics
Skyrmion physics
```

---

## 推荐写

```text
physics-inspired artificial material dynamics
precomputed material-state trajectory
history-dependent defect dynamics
chroma-driven analytical potential field
continuous geometry morphing
```

---

# 102. 旧蓝图文档可以继续保留

但是 README 不要把：

```text
blueprint 存在
```

当成：

```text
implementation 完成
```

---

# 103. 本轮禁止事项

为了防止再次横向扩张：

- 不新增新的 phase；
- 不新增新的 visual preset；
- 不写真正 Chladni；
- 不写 Navier–Stokes；
- 不写 Skyrmion；
- 不写新 GUI；
- 不做 3D；
- 不做 ML genre classifier；
- 不引 PyTorch；
- 不重新设计播放器；
- 不大规模重构 Qt；
- 不做 GPU particle renderer；
- 不新增 20 个 dataclass；
- 不新建 `V3` 与现有 V2 并存。

---

# 104. 本轮允许新增文件的上限思路

只有确实需要时新增少量：

```text
app/dynamics/geometry.py       # 如果现有 GeometryControl 无合适位置
tests/test_v2_runtime_pipeline.py
tests/test_seek_equivalence.py
tests/test_export_equivalence.py
scripts/plot_v2_trajectory.py
```

其余优先修改现有文件。

---

# 105. 本轮结束时，仓库结构应该更“少双轨”，而不是更多

理想：

```text
app/analysis/
    source features

app/dynamics/
    visual context
    material trajectory
    analytical field
    deterministic math

app/visual/
    scene
    particles
    geometry rendering
    Qt painting

app/export/
    deterministic time traversal
```

而不是：

```text
old phase
new phase
experimental phase
gpu phase
legacy phase
phase v3
```

---

# 106. 最关键的代码审查问题

开发 Agent 每完成一个阶段都自问：

> **“我刚写的这个对象，正常从 UI 打开一首歌以后真的会被调用吗？”**

如果答案是：

```text
只有 test 调用
```

那不能算产品功能完成。

---

# 107. 第二个关键审查问题

> **“如果我把旧 PhaseEngine/PESField 故意抛异常，默认 V2 播放还正常吗？”**

最终答案必须：

```text
Yes
```

---

# 108. 第三个关键审查问题

> **“Renderer 看到的是 Audio Features，还是 Material State？”**

V2 主体 geometry 最终答案应该：

```text
Material State
```

快速 transient event 除外。

---

# 109. 第四个关键审查问题

> **“同一时刻 t，换 30fps/60fps 会不会得到另一条 material trajectory？”**

答案必须：

```text
No
```

---

# 110. 第五个关键审查问题

> **“Seek 后有没有继承 seek 前的宏观世界？”**

答案必须：

```text
No
```

---

# 111. 第六个关键审查问题

> **“并行导出的 segment 是否靠 5 秒 warmup 猜 material phase？”**

答案必须：

```text
No
```

只允许短寿 particles/effects 用 warmup。

---

# 112. 第七个关键审查问题

> **“Plasma 状态 tonal confidence 低时，力场是不是一起没了？”**

答案必须：

```text
No
```

potential、curl、stochastic 独立 gate。

---

# 113. 第八个关键审查问题

> **“spectral contrast 和 band ratio 的变量名是否真的符合数值语义？”**

答案必须：

```text
Yes
```

---

# 114. Round 2 最终自动测试清单

至少：

```text
test_rms_calibration_reference
test_spectral_contrast_normalized_range
test_raw_band_share_sum
test_l3_causal_no_future_leak
test_l3_equal_timeline
test_l3_tail_nonzero
test_window_interpolation
test_real_section_progress
test_no_fake_beat
test_visual_context_uses_real_l3_l4
test_material_hysteresis
test_material_state_invariants
test_trajectory_query_interpolation
test_trajectory_fps_independence
test_pes_analytic_vs_numeric_gradient
test_pes_zero_activity
test_pes_fluid_curl
test_pes_plasma_force
test_deterministic_particle_random
test_legacy_phase_not_used_by_default
test_legacy_pes_not_used_by_default
test_seek_material_equivalence
test_serial_parallel_material_equivalence
```

---

# 115. Round 2 最终人工验收清单

至少用 4~8 首差异明显的歌曲：

```text
[ ] 不同歌曲主体结构明显不同
[ ] 同一首歌不同 section 主体结构会演化
[ ] phase transition 连续，不像三个 preset 切换
[ ] 高潮结束后存在可感知“冷却/恢复”
[ ] 静音不会变成 fluid vortex
[ ] ambient 不会 fake 120 BPM pump
[ ] noisy/plasma 段落仍有强运动
[ ] seek 后画面与该时间位置合理
[ ] 串行/并行 segment 无明显接缝
[ ] 30fps/60fps 宏观结构一致
```

---

# 116. 不要为了“测试绿”把阈值写得毫无意义

例如：

```python
assert difference < 100000
```

这种测试没有价值。

像 analytical gradient：

必须真的在合理误差内比较。

像 seek equivalence：

必须明确比较哪些 state。

---

# 117. 对当前测试中发现的具体问题：必须修

现有 analytical PES test：

虽然计算了 numerical reference，

但如果最终只 assert：

```text
not NaN
not inf
```

不算 gradient test。

改掉。

---

# 118. 对当前 `test_visual_context` 的具体要求

不要再只用：

```text
constant RMS = 0.5
```

增加至少：

```text
dynamic RMS ramp
silence segment
energy step
onset pulses
```

避免 calibration bug 被 degenerate percentile branch 掩盖。

---

# 119. 建议增加测试 helper

例如：

```text
tests/fixtures/synthetic_features.py
```

生成 deterministic：

- harmonic；
- percussive；
- noise；
- mixed；
- silence；
- section boundaries。

这样各测试不重复造数组。

---

# 120. Error handling

如果 dynamics compile 遇到：

```text
empty features
0 duration
all-zero RMS
missing L3/L4 old cache
```

必须 graceful。

---

## 旧 cache 兼容策略

如果 cache 缺新字段：

### 推荐

明确识别旧 cache version 并重新分析。

不要：

```text
novelty=0
energy_slow=fast*0.8
```

默默 fallback 后声称 V2。

---

# 121. 为什么本轮不推荐大量 placeholder fallback

开发早期 placeholder 有价值。

但现在问题是：

> placeholder 已经让“类看起来完整”。

因此 Round 2 应宁可：

```python
raise MissingFeatureError
```

在开发模式暴露问题，

也不要偷偷补假数据。

---

# 122. Production fallback 可以存在，但必须可观测

例如：

```text
warning:
V2 dynamics unavailable for legacy cache; reanalysis required
```

而不是 silent degradation。

---

# 123. 日志建议

不要每 frame print。

在加载一首歌后一次性打印：

```text
Dynamics V2 enabled
trajectory ticks: ...
simulation_hz: ...
phase occupancy estimate: ...
legacy phase engine: disabled
analytical field: enabled
```

方便确认真实路径。

---

# 124. 以后不要用注释声称一个功能已经实现

例如：

```text
# analytical gradient
```

必须与代码一致。

如果暂时 numerical：

```text
# finite-difference prototype
```

诚实标注。

---

# 125. 性能 profiling 建议

本轮集成完成后再测：

```text
context lookup
material lookup
field prep
field sample for 500/1000/1600 particles
geometry build
paint
```

避免只测总 FPS，不知道瓶颈。

---

# 126. 若 particle force 仍超预算

优先：

1. 预计算 Fourier；
2. batch numpy；
3. coarse vector grid；
4. 只对部分粒子施加强 field；
5. 降 particle count。

不要马上 CUDA/GLSL。

---

# 127. VisualContext/MaterialTrajectory 内存不是主要问题

假设：

```text
60 Hz
5 min
≈18,000 states
```

每 state 十几个 float，

规模很小。

不要为了几 MB 提前做复杂压缩。

---

# 128. MaterialTrajectory 应尽量 immutable

编译完：

```text
read-only
```

播放过程中不能因为 Renderer 改参数偷偷 mutation。

如果用户改变 dynamics 参数：

```text
重新 compile
```

---

# 129. V2 参数集中管理

不要把：

```text
heal_tau
damage_rate
prototype centers
curl gain
plasma noise
```

散落在五个文件。

本轮可以集中：

```text
DynamicsConfig
```

但如果当前已有相对集中常量，不必为了形式重构。

---

# 130. 不建议现在做用户可调参数 UI

这些参数目前还是开发参数。

先把模型调到合理默认值。

以后再考虑 advanced settings。

---

# 131. Geometry morph 参数也不要一次暴露几十个 slider

否则项目又变成：

> 特效调参器

而不是 coherent physical visualizer。

---

# 132. Round 2 完成后的预期效果

如果本轮正确完成，即使尚未加入真正 Chladni/Shader，用户也应该已经能看到：

```text
安静有调性段落：
结构更规则、稳定、锁相

groove / 中等运动：
整体开始连续扭曲、旋流

强烈高潮：
缺陷积累、结构断裂、粒子散射

高潮结束：
不是瞬间恢复
而是逐渐退火、重建
```

这时同质化才开始真正下降。

---

# 133. 如果完成后“看起来仍然几乎一样”，怎么办？

不要先加新特效。

依次检查：

1. Material trajectory 是否真的动态；
2. phase occupancy 是否 collapse；
3. GeometryControl 是否数值变化；
4. Renderer 对 GeometryControl gain 是否太弱；
5. VisualDNA prior 是否仍压过 MaterialState；
6. 是否叠了太多 smoothing。

---

# 134. 如果变化太疯怎么办？

同样不要增加更多规则。

优先：

- 降 geometry gain；
- 增加 coherence；
- 延长 defect recovery；
- 降 fast transient 对宏观 state 的权重；
- 将某些影响转成短局部 effect。

---

# 135. 本轮不需要追求“最终艺术风格”

Round 2 的成功标准是：

> 架构与动态真实生效。

真正的美术精修：

- palette；
- Chladni；
- glow；
- GPU；
- render quality；

可以在 Round 3 做。

---

# 136. Round 2 最终文件级修改地图

预计至少涉及：

```text
app/analysis/beat.py
app/analysis/spectrum.py
app/analysis/window.py
app/analysis/features.py
app/analysis/extractor.py

app/dynamics/calibration.py
app/dynamics/context.py
app/dynamics/material.py
app/dynamics/trajectory.py
app/dynamics/field.py
app/dynamics/deterministic.py

app/visual/scene.py
app/visual/particles.py
app/visual/ring_layer.py
app/visual/renderer.py
app/visual/energy_core.py   # 若需要

app/ui/main_window.py
app/export/video_exporter.py

tests/...
scripts/...
```

如果最终 commit 完全没有改：

```text
renderer.py
particles.py
main_window.py
video_exporter.py
```

却声称“full V2 integration complete”，应视为明显未完成。

---

# 137. Round 2 最终架构图

目标必须真实变成：

```text
                     ┌───────────────────┐
                     │   Audio Analysis  │
                     │ L1/L2/L3/L4/L5    │
                     └─────────┬─────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  TrackCalibration   │
                    └─────────┬───────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │ VisualContextBuilder│
                    └─────────┬───────────┘
                              │
                 whole-track  │
                 compile      ▼
                    ┌─────────────────────┐
                    │ MaterialTrajectory  │
                    │ order/excitation/...│
                    └───────┬───────┬─────┘
                            │       │
                         at(t)      │
                            │       │
             ┌──────────────┘       └─────────────┐
             ▼                                    ▼
    ┌─────────────────┐                  ┌──────────────────┐
    │ GeometryControl │                  │ Analytical Field │
    └────────┬────────┘                  └─────────┬────────┘
             │                                     │
             ▼                                     ▼
    ┌─────────────────┐                  ┌──────────────────┐
    │ Renderer / Ring │                  │ Particle System  │
    └────────┬────────┘                  └─────────┬────────┘
             │                                     │
             └──────────────────┬──────────────────┘
                                ▼
                       ┌─────────────────┐
                       │   Final Frame   │
                       └─────────────────┘
```

Seek / export 均从同一：

```text
absolute time -> context/material
```

查询。

---

# 138. 这轮最核心的四个原则

如果文档太长，只记下面四条。

---

## 原则 1

**不再新增平行架构，必须让现有 V2 进入真实主链。**

---

## 原则 2

**所有变量名必须匹配真实数据语义，禁止 placeholder 冒充 L3/L4。**

---

## 原则 3

**宏观 material trajectory 与 render FPS / seek / export 解耦。**

---

## 原则 4

**最终画面必须由 MaterialState 改变 geometry，而不只是 HUD 数值改变。**

---

# 139. 给开发 Agent 的最后执行摘要

当前 `a94b14f` 已经很好地完成了 V2 的数学与架构原型，但主程序仍主要运行旧 Phase/PES/Renderer 链路。本轮不要继续增加新的物理概念，而应集中做**纵向集成**。

第一阶段先修：

```text
RMS calibration reference
spectral contrast
raw band share
L3 causal/equal timeline/interpolation
真实 L4 context
```

然后让：

```text
FeatureCache
    ↓
VisualContextBuilder
    ↓
MaterialTrajectoryCompiler
```

在正常加载歌曲时真正执行。

接着迁移 Scene，使它按绝对时间查询：

```text
VisualContext + MaterialState
```

而不是调用旧 PhaseEngine。

随后把 AnalyticalPES 接入 ParticleSystem，并将 force 拆为：

\[
F =
F_\mathrm{potential}
+
F_\mathrm{curl}
+
F_\mathrm{plasma}
\]

其中 tonal confidence 只主要 gate conservative tonal field，不能让 Fluid/Plasma 一起消失。

之后必须让：

```text
GeometryControl
```

真正改变 Renderer 的：

```text
symmetry
coherence
circulation
fragmentation
defects
roughness
```

并把旧 `structure_type` 降级为弱 global prior。

最后接入 keyed deterministic randomness、stable particle IDs、Seek transient rebuild 和 parallel export，使所有运行模式共享同一个预编译 Material trajectory。

**Round 2 结束时，请用“默认运行路径是否真实调用 V2”而不是“新类是否存在”判断完成度。**

如果：

```text
renderer.py
particles.py
main_window.py
video_exporter.py
```

仍基本没被修改，

那么本轮一定还没有真正完成。

---

# 140. 最终验收句

本轮真正完成之后，应当可以准确地说：

> **Stormy-Pulse V2 no longer computes its visual phase inside the renderer loop. The full track is first transformed into a calibrated, multiscale VisualContext and a deterministic, history-dependent MaterialTrajectory. Rendering, particle dynamics, seeking, and parallel export all query the same physical state at absolute time, while continuous GeometryControl morphs one visual world instead of switching between fixed presets.**

在代码确实满足这句话以前，请不要提前宣告 V2 integration complete。
