# Stormy-Pulse V2 Round 4：运行时稳定化、Renderer 闭环与可复现性验收计划

> **文档性质**：第四轮 GitHub 源码审计后的执行计划，可直接交给开发 Agent  
> **审计基线**：2026-08-26 当前 GitHub `main` 分支 raw source  
> **前置文档**：
> - `STORMY_PULSE_V2_IMPLEMENTATION_BLUEPRINT.md`
> - `STORMY_PULSE_V2_ROUND2_INTEGRATION_PLAN.md`
> - `STORMY_PULSE_V2_ROUND3_CLOSE_THE_LOOP_PLAN.md`
>
> **Round 4 的主题不是继续扩展，而是：**
>
> \[
> \boxed{\text{Make it run} \rightarrow \text{Make it correct} \rightarrow \text{Make the geometry respond} \rightarrow \text{Make it reproducible}}
> \]
>
> 当前代码已经跨过“V2 只是实验模块”的阶段，但尚未跨过“V2 是完整、稳定、可验证的默认运行系统”的阶段。

---

# 0. 本轮源码审计总评

当前 `main` 相比上一轮确实有明显进步：

## 已真实完成或基本完成

- L3 rolling windows 已改成 trailing causal；
- 2/4/8 s L3 使用统一 1 Hz 时间轴；
- `VisualContext` 开始读取真实 L3 energy / transient density / beat density；
- `MaterialStateEngine` 已真实使用：
  - `energy_slow`
  - `energy_trend`
  - `transient_density`
  - `beat_density`
  - `novelty`
  - `boundary_impulse`
- `MaterialStateSequence` 已实现时间插值；
- `build_dynamics_bundle()` 已集中 MainWindow / Exporter 的 V2 bundle 创建；
- track seed 已改为基于稳定 BLAKE2，而不是 Python `hash(path)`；
- Analytical field 已把 tonal potential 与 fluid curl 的 gain 分开；
- `w_plasma` 已真正进入 force decomposition；
- Scene / MainWindow / Sequential Export / Parallel Export 已经真实走 V2 MaterialTrajectory；
- legacy `PhaseEngine` 已经主要退化成 bundle 缺失时的 fallback；
- analytical gradient test 已开始真正与 numerical finite-difference reference 比较；
- Particle drag 已从可能变负的线性 factor 改为指数形式。

这些都应保留，不要推倒重来。

---

# 1. 但是当前 `main` 存在一个 Release-Blocking Runtime Regression

这是本轮第一优先级，必须在任何其他修改之前修复。

---

## 1.1 当前调用方

`app/visual/scene.py` 当前会调用：

```python
self.ring_layer.update(
    ...,
    phase_state=self.phase_state,
    material=active_material,
    geometry=self.current_geometry_control,
)
```

也就是说调用方已经认为：

```text
RingLayer.update()
```

支持：

```text
material=
geometry=
```

---

## 1.2 当前被调用方

但是 `app/visual/ring_layer.py` 当前签名仍然是：

```python
def update(
    self,
    time,
    bass,
    mid,
    high,
    onset,
    centroid,
    rolloff,
    dt=0.016,
    phase_state=None,
):
```

没有：

```text
material
geometry
```

---

## 1.3 直接后果

默认运行路径一旦进入：

```python
Scene.update()
```

理论上就会：

```text
TypeError:
RingLayer.update() got an unexpected keyword argument 'material'
```

这不是“艺术效果还没完成”，而是**主运行链契约不一致**。

---

# 2. P0-0：先建立 Runtime Smoke Gate

在继续开发之前：

```bash
uv run pytest
```

必须完整跑一次。

如果当前环境不能跑全部 GUI tests，也至少：

```bash
uv run pytest \
    tests/test_v2_runtime_pipeline.py \
    tests/test_round3_closure.py
```

不能只运行某几个 dynamics 单元测试后宣告完成。

---

## 2.1 新增一个最小不可逃避 smoke test

建议：

```text
tests/test_scene_v2_smoke.py
```

它只做：

```python
scene = Scene(...)
scene.set_global_features(...)
scene.set_dynamics_bundle(...)
scene.update(one_valid_frame, ...)
```

然后 assert：

```text
没有 exception
current_material_state is not None
current_geometry_control is not None
```

这个测试会直接抓住当前 `RingLayer.update()` contract mismatch。

---

# 3. 为什么当前测试体系没有保护住这个 bug？

当前仓库已经存在会调用：

```python
scene.update(...)
```

的 V2 runtime tests。

按当前源码组合，它们也应该经过：

```text
Scene.update
    ↓
RingLayer.update(material=..., geometry=...)
```

因此如果完整测试真的在当前 HEAD 上运行，这一不匹配应该被发现。

---

## 本轮要求

开发 Agent 完成修改后必须报告：

```text
1. 实际执行的测试命令
2. passed / failed 数量
3. 如果有 skipped，列出原因
```

不能只说：

> “Tests added.”

也不能只说：

> “Logic verified.”

---

# 4. P0-1：修复 RingLayer 契约，但不要只加两个没用的参数

最差的修法是：

```python
def update(..., material=None, geometry=None):
    pass
```

然后把 TypeError 消掉。

这只能叫：

> “API crash fixed”

不能叫：

> “GeometryControl integrated.”

---

# 5. RingLayer 应真正接入 GeometryControl

推荐：

```python
def update(
    self,
    time: float,
    bass: float,
    mid: float,
    high: float,
    onset: float,
    centroid: float,
    rolloff: float,
    dt: float = 0.016,
    *,
    material=None,
    geometry=None,
    legacy_phase_state=None,
):
```

V2 时优先：

```text
geometry
```

legacy 时才：

```text
legacy_phase_state
```

---

# 6. RingLayer 第一版至少让这些变量真实生效

## `symmetry`

影响：

```text
环上重复结构的规则程度
mode / lobe 的整数锁定程度
segment spacing regularity
```

---

## `coherence`

影响：

```text
多层 ring/shell 之间的 phase consistency
线条连续性
局部 perturbation correlation
```

---

## `circulation`

影响：

```text
环相位的额外旋转
angular shear
spiral deformation
```

---

## `fragmentation`

影响：

```text
broken segments
arc gaps
line split
```

---

## `roughness`

影响：

```text
局部 radius perturbation
细尺度边缘不稳定
```

---

## `angular_lock`

影响：

```text
稳定方向
chroma / Fourier angular field 对 shell 的锁定程度
```

---

# 7. `broken_segments` 终于应该真正工作

当前 `RingLayer` 有：

```python
self.broken_segments
```

但基本没有真正动态来源。

本轮应让：

```text
MaterialState.defect_density
GeometryControl.fragmentation
```

共同驱动。

---

# 8. 但禁止每帧重新随机 broken segments

否则：

```text
defect
```

只是闪烁噪声，不是具有寿命的材料缺陷。

---

## 第一版可采用 deterministic coarse-time mask

例如：

```python
damage_epoch = int(time / 0.25)
```

对 segment `i`：

```python
u = deterministic_float(
    track_seed,
    "ring_damage",
    damage_epoch,
    i,
)
```

然后根据：

```text
fragmentation
```

决定该 segment 的 defect target。

下一 epoch 再缓慢 morph。

---

# 9. 当前更大的 V2 断点：Renderer 仍完全不知道 GeometryControl

当前 `renderer.py` 仍没有系统读取：

```text
current_material_state
geometry_control
fragmentation
circulation
coherence
```

这意味着：

> V2 的宏观 MaterialState 目前主要只影响粒子，而主体几何仍然基本是 V1。

---

# 10. 这也是当前反同质化尚未真正完成的根本原因

现在的主视觉仍主要是：

```text
VisualDNA.structure_type
    ↓
reactor / vortex / organic / pulse
```

也就是整首歌先选一种结构 basis。

MaterialTrajectory 虽然已经很先进，

但如果 Renderer 不看它：

```text
宏观状态变化
```

就无法变成：

```text
宏观结构变化
```

---

# 11. P0-2 / P1：真正完成 Renderer Geometry Closure

本轮必须修改：

```text
app/visual/renderer.py
```

这是一个硬验收条件。

如果下一次提交仍然几乎没改 `renderer.py`，

不能宣告 Round 4 完成。

---

# 12. 不需要一次性重写 2000 行 Renderer

先选三个最有影响的层：

```text
1. harmonic shell
2. generative structure
3. transient lattice
```

让 MaterialState 真正改变它们。

---

# 13. Harmonic Shell 最低映射

例如：

```text
symmetry
→ lobe integer regularity

angular_lock
→ mode phase stability

coherence
→ shell-to-shell phase alignment

circulation
→ angular warp / twist

fragmentation
→ local missing arcs

roughness
→ high-frequency radial deformation
```

---

# 14. Generative Structure 最低映射

保留：

```text
reactor
vortex
organic
pulse
```

作为 **style basis**。

但是每一种 basis 都必须被 MaterialState 改变。

---

## 例：同一个 Reactor

### Crystal-like

```text
规则
径向对齐
高对称
低 broken segment
```

### Fluid-like

```text
spiral / shear
高 circulation
结构连续但发生 advection
```

### Plasma-like

```text
fragmentation
rough edge
局部 coherence collapse
```

这样：

```text
structure_type
```

不再等于：

> 整首歌从头到尾的 topology。

---

# 15. Transient Lattice 是最适合 defect 的现有层

让：

```text
defect_density
```

真实改变：

- local line offset；
- missing connection；
- symmetry break；
- phase slip；
- line continuity。

---

# 16. 当前测试里的 `test_geometry_control_renderer_morph` 名不副实

当前所谓 renderer morph test 实际上主要只是检查：

```text
GeometryControl fields are within [0,1]
```

它没有证明：

```text
Renderer geometry 真的改变
```

---

# 17. 这个测试必须重写

有两种推荐方案。

---

## 方案 A：抽纯 Geometry Descriptor

推荐。

例如：

```python
descriptor = renderer.compute_harmonic_shell_geometry(
    ...
    geometry=geometry,
)
```

返回：

```text
angles
radii
lobe amplitudes
segment mask
warp
```

测试：

```text
crystal descriptor != fluid descriptor
fluid descriptor != plasma descriptor
```

---

## 方案 B：离屏 QImage render compare

如果当前 Qt test 环境稳定：

分别渲染：

```text
Crystal / Fluid / Plasma
```

比较 raw RGBA image。

至少保证 pixel difference 超过有意义阈值。

---

# 18. 第一方案更推荐

原因：

- 不依赖 GPU；
- 不依赖窗口；
- CI 稳；
- 将来 GLSL 也可以复用 Geometry Descriptor。

---

# 19. 已经完成：L3 causal rewrite，保留

当前 `window.py` 已经真正改成：

```text
[t-W, t]
```

并统一 2/4/8 秒时间轴。

这个上一轮问题已经修复。

**不要再重写。**

---

# 20. 但 L3 查询 interpolation 仍没有真正实现

这是一个明确未完成项。

当前：

```python
FeatureCache.get_window_stats_at_time()
```

仍然使用近似：

```python
idx = int(time)
```

或等价整数 index lookup。

---

# 21. 当前测试已经要求 4.5s 插值

也就是说：

```text
test intent
```

与：

```text
implementation
```

不一致。

---

# 22. P0-3：实现真正插值

不要假设：

```text
times_1hz == integer index
```

使用实际：

```python
times = window_features.times_1hz
```

---

## 推荐：

```python
idx = np.searchsorted(times, time)

if idx <= 0:
    return first

if idx >= len(times):
    return last

t0, t1 = times[idx-1], times[idx]
u = (time-t0)/(t1-t0)

value = (1-u)*v0 + u*v1
```

---

# 23. 对所有 scalar window statistics 使用统一插值

包括：

```text
energy_mean
energy_trend
brightness_mean
brightness_trend
spectral_activity
beat_density
transient_density
chaos_proxy
```

---

# 24. P0-4：当前 cache version 没有随着 L3 语义变化而 bump

这是非常重要且容易被忽略的问题。

---

## 24.1 当前现实

旧 cache version：

```text
v4
```

仍然可以被加载。

但是：

```text
v4 旧 cache
```

可能包含上一代 forward-looking L3 windows。

而新代码认为它们是：

```text
causal trailing L3
```

---

# 25. 后果

老用户升级程序以后：

```text
代码已经修成 causal
```

但：

```text
磁盘旧 cache 继续返回旧 forward-looking stats
```

于是新 MaterialTrajectory 仍会获得错误时间语义。

---

# 26. 这是数据 schema / semantic migration

因此必须：

```python
CACHE_VERSION = "v5"
```

或下一个版本。

---

# 27. 同时去掉 extractor 里的硬编码 version

不要同时存在：

```python
CACHE_VERSION = "v5"
```

和：

```python
cache_version="v4"
```

---

## 单一来源

```python
from app.core.constants import CACHE_VERSION
```

然后 metadata：

```python
cache_version=CACHE_VERSION
```

---

# 28. 新增 cache migration test

创建：

```text
old v4 cache
```

确保当前：

```text
v5 runtime
```

拒绝加载并重新分析。

---

# 29. 当前 tests 使用的 metadata version 也不统一

测试中出现：

```text
v5
2.0
```

而真实 runtime 还是：

```text
v4
```

这种测试 fixture 漂移应该清理。

---

# 30. P0-5：Scene.seek_to() 当前存在严重递归/重建逻辑漏洞

这是本轮第二个非常重要的 runtime issue。

---

# 31. 当前大致流程

`seek_to(target)`：

```text
self.time = target
```

然后决定：

```text
warmup_start = target - 2s
```

再循环：

```text
warmup_start -> target
```

每个 warmup frame 调：

```python
self.update(frame)
```

---

# 32. 但是 `Scene.update()` 自己有 backward-time 检测

大意：

```python
if frame.time < self.time:
    self.seek_to(frame.time)
```

---

# 33. 因此第一次 warmup frame：

```text
frame.time = target - 2
self.time  = target
```

满足：

```text
frame.time < self.time
```

于是：

```text
seek_to(target)
    ↓
update(target-2)
    ↓
seek_to(target-2)
    ↓
update(target-4)
    ↓
seek_to(target-4)
    ...
```

这会形成递归式向前/向后重建，

直到接近 0。

---

# 34. 这不是设计上的小瑕疵

如果用户 seek 到：

```text
120s
```

理论上可能触发几十层嵌套 seek/rebuild。

对于更长音乐甚至可能产生：

- 巨量无意义工作；
- stack 深度增长；
- 状态不确定；
- 卡顿。

---

# 35. P0-5 修复原则

**Warmup 期间绝不能触发 seek detection。**

---

# 36. 推荐重构为三个明确动作

```python
scene.reset_transient_state()
scene.simulate_tick(...)
scene.rebuild_to_time(...)
```

---

# 37. `rebuild_to_time()` 推荐逻辑

```text
target = requested time
warmup_start = max(0, target - W)

reset transient state

self.time = warmup_start

for t in warmup_start ... target:
    query context/material at t
    simulate visual tick with allow_discontinuity_detection=False

self.time = target
```

---

# 38. 不要先：

```python
self.time = target
```

再模拟过去。

---

# 39. 更干净的方案：内部私有 simulation path

例如：

```python
_update_internal(
    ...,
    detect_seek: bool,
)
```

正常播放：

```text
detect_seek=True
```

warmup：

```text
detect_seek=False
```

---

# 40. P0-6：Seek warmup 当前硬编码 1920×1080

当前内部 warmup：

```text
width=1920
height=1080
```

这对于：

- 竖屏；
- 4K；
- 自定义 export；
- resize 后实时播放；

都不正确。

---

# 41. Scene rebuild 必须接收真实 viewport

例如：

```python
scene.rebuild_to_time(
    target,
    width=current_width,
    height=current_height,
)
```

---

# 42. 或者把 simulation 完全改成 normalized coordinates

这是更长远方案，

但本轮没必要为了这个大重构。

先传真实尺寸即可。

---

# 43. P0-7：Exporter 现在存在“双重 warmup”

并行 worker 已经：

```text
scene.seek_to(warmup_start)
```

而当前 `scene.seek_to()` 自己又做：

```text
2s internal warmup
```

之后 exporter 外部还会：

```text
warmup_start -> segment_start
```

继续 preroll。

---

# 44. 必须规定 warmup ownership

推荐：

> **Scene owns visual rebuild. Exporter only asks for state at target.**

即：

```python
scene.rebuild_to_time(segment_start, width, height)
```

然后直接从 segment_start 开始输出。

---

# 45. 或者反过来

Scene 只：

```text
reset_at(warmup_start)
```

Exporter 完整负责 preroll。

---

# 46. 只能选一种

不要两层各 warmup 一次。

---

# 47. 推荐 Scene owning rebuild

这样：

```text
MainWindow Seek
Sequential Export
Parallel Export
```

全部共用同一逻辑。

---

# 48. P0-8：silent track calibration 仍然有语义 bug

当前 `TrackCalibration.normalize_rms_db()`：

当：

```text
P95 - P10 ≈ 0
```

时返回：

```text
0.5
```

---

# 49. 对 constant nonzero signal 这还勉强合理

但是全静音：

```text
RMS == 0
```

也会进入类似 branch。

那么：

```text
energy_fast ≈ 0.5
activity ≈ 0.8
```

这显然违背：

```text
silence -> dormant
```

---

# 50. 修复

Calibration 保存：

```python
is_silent_track: bool
```

或根据：

```python
rms_reference <= SILENCE_RMS_EPS
```

特殊处理。

---

## 全静音：

```python
normalize_rms_db(...) = 0.0
```

---

# 51. 增加 test

```python
rms = np.zeros(...)
```

最终：

```text
VisualContext.activity ≈ 0
MaterialState.excitation → 0
```

---

# 52. P0-9：TrackCalibration 对 all-NaN flux/onset 的防御仍不完整

当前代码先：

```text
filter NaN
```

但是否调用 percentile 主要仍可能依赖原数组长度。

---

# 53. 正确写法

```python
valid_flux = flux_arr[np.isfinite(flux_arr)]

if valid_flux.size:
    flux_p95 = np.percentile(valid_flux, 95)
else:
    flux_p95 = safe_default
```

onset 同理。

---

# 54. 这一条也加 test

输入：

```text
[NaN, NaN, NaN]
```

不应该 exception。

---

# 55. 已修：spectral contrast global normalization

这一项和上一轮不同。

当前 extractor 已经对：

```text
frame-wise spectral contrast
```

做 P10/P95 normalize，

然后再得到：

```text
global_contrast ∈ [0,1]
```

所以此前：

```text
raw librosa contrast > 0.45
```

的严重尺度错误基本已经修掉。

---

# 56. 不要重复重做 spectral contrast

本轮只需要增加：

```text
range / non-saturation test
```

确保真实曲目不会全都贴 0 或 1。

---

# 57. 仍未修：band ratio 仍然不是 raw power share

当前：

```text
compute_band_energies_6
```

还是返回每频带自己归一化后的 `drive`。

Global：

```text
bass_ratio
mid_ratio
high_ratio
```

仍基于这些 drive 的均值比较。

---

# 58. P1-1：实现 band_drive 与 band_share 分离

推荐 `spectrum.py` 返回：

```text
band_drive_6
raw_band_power_6
```

再构造：

```text
band_share_6
```

---

## Band drive

用于：

```text
即时视觉响应
```

保留现有独立归一化。

---

## Band share

用于：

```text
全曲频谱平衡
spectral tilt
VisualDNA global prior
```

---

# 59. GlobalFeatureSet 中的 bass/mid/high ratio

应来自：

```text
raw power share
```

而不是：

```text
independently normalized drive
```

---

# 60. VisualContext.spectral_tilt 也应改

当前近似：

```python
high_drive / (bass_drive + high_drive)
```

同样混入 drive normalization。

---

## 应改为：

```text
raw spectral share based tilt
```

---

# 61. 如果不想往 FrameFeatureSequence 再塞 6 个 raw power

可以单独存在：

```text
SpectralBalanceSequence
```

但不要为了形式新增复杂层。

---

# 62. 可以简单给 `FrameFeatureSequence` 增 `band_shares`

例如：

```python
band_shares: np.ndarray  # shape (N, 6)
```

这比改变 30D feature vector更干净。

---

# 63. P1-2：Event lookup 仍然是 symmetric ±80ms

当前：

```text
get_events_near(time, 0.08)
```

意味着：

```text
未来 80ms 内的 beat
```

可能提前成为当前 beat。

---

# 64. 对快速视觉这会造成抢拍

特别是：

```text
beat burst
onset flash
```

---

# 65. 推荐增加 causal event API

例如：

```python
get_events_crossed(
    previous_time,
    current_time,
)
```

返回：

```text
previous_time < event_time <= current_time
```

---

# 66. VisualContext 的 beat_impulse

使用最近**已经发生**的 beat：

\[
I(t)=s e^{-(t-t_b)/\tau}, \quad t\ge t_b
\]

不要未来对称窗口。

---

# 67. L3 density 已经 causal，所以保留

这里无需改。

---

# 68. P1-3：当前 Plasma “stochastic” 仍然不是真随机散射

field.py 当前 Plasma term 已经实际进入 force。

这是进步。

但是：

```text
sin(r, theta)
cos(r, theta)
```

本质上是：

> 静态空间波纹/散射场

不是 stochastic。

---

# 69. 两种选择

## 方案 A：诚实改名

```text
plasma_wave_scattering
```

这是最简单安全的。

---

## 方案 B：实现真正 deterministic stochastic kick

推荐放 ParticleSystem，

而不是 PESField。

---

# 70. 为什么更适合放 ParticleSystem

Potential / curl field：

```text
是空间场
```

stochastic scattering：

```text
是每粒子的时间相关扰动
```

它应该依赖：

```text
particle_id
simulation_tick
track_seed
```

---

# 71. 这要求 stable Particle ID

当前 Particle 还没有稳定 ID。

新增：

```python
particle_id: int
```

ParticleSystem：

```python
next_particle_id += 1
```

---

# 72. 不要用 list index

因为粒子死亡后：

```text
list index
```

会改变。

---

# 73. P1-4：deterministic.py 已存在，但产品仍大量使用 global random

当前：

```text
Scene
ParticleSystem
Renderer
```

都有：

```python
random.random()
random.uniform()
```

---

# 74. 这意味着当前仍不能声称 deterministic rendering

虽然：

```text
track seed
```

已经稳定，

但 seed 没有真正控制大部分 visual randomness。

---

# 75. 必须把随机调用分类

## Simulation-critical

必须 keyed deterministic：

- ambient particle emission；
- particle angle；
- particle speed；
- particle size/lifetime；
- burst spread；
- plasma stochastic kick；
- defect mask。

---

## Render-only

也应该按：

```text
track_seed + frame/tick + item_index
```

稳定：

- decorative spikes；
- fine grain jitter；
- high-frequency ornaments。

---

# 76. Renderer 当前 atmosphere 仍每帧直接 global random

这会产生：

```text
同一帧重画两次
```

装饰都不同。

而且：

```text
串行
并行
实时
```

无法严格复现。

---

# 77. 不要通过 `random.seed()` 每帧解决

使用 stateless deterministic function。

---

# 78. P1-5：当前 Scene ambient emission 仍然 frame-probability based

例如：

```python
if random() < p:
    emit()
```

60 FPS 比 30 FPS 每秒抽更多次。

---

# 79. 用 Poisson rate

如果期望：

```text
lambda events / sec
```

则：

\[
p(dt)=1-e^{-\lambda dt}
\]

这样不同 FPS 下单位时间事件率一致。

---

# 80. 已修一部分：Particle drag

当前：

```python
drag_factor = drag ** sf
```

比上一轮好。

保留。

---

# 81. 但 Particle update 仍总体 render-dt driven

这不一定必须 Round 4 全部重写固定步长。

可以先做：

- dt-aware emission；
- deterministic RNG；
- stable particle id；
- 30 vs 60 FPS macro statistics test。

---

# 82. 如果测试仍差异明显，再上 fixed-step accumulator

不要过早重构。

---

# 83. P1-6：MaterialStateSequence interpolation 已完成

这一项通过。

不要再重写。

---

# 84. P1-7：MaterialState 已真实使用 L3/L4

这一项也通过。

当前：

- energy_slow；
- energy_trend；
- transient density；
- beat density；
- novelty；
- boundary impulse；

已进入 Material dynamics。

---

# 85. 但 `climax_prior` / `section_progress` 不一定非要进入 MaterialState

这不是 bug。

它们可以保留给：

```text
Renderer
or later weak prior
```

不要为了“每个字段都必须用”强行塞权重。

---

# 86. P1-8：boundary impulse 当前基本因果，保留

当前已经以：

```text
current section start
```

之后衰减为主。

比上一轮对下一 section endpoint 做对称距离更合理。

---

# 87. Novelty time axis 仍是近似映射

当前：

```text
time × len(novelty)/duration
```

通常够用。

但更严谨：

```text
SectionFeatureSet.novelty_times
```

可以后再加。

不是 blocker。

---

# 88. P1-9：DynamicsBundle factory 已集中，保留

MainWindow / sequential / parallel 已共用。

这是上一轮要求，已经通过。

---

# 89. 但 V2 compile failure 仍可能 silent fallback legacy

开发阶段建议：

```text
STRICT_V2
```

默认为 tests / dev 开启。

---

# 90. Dev mode 下

V2 bundle build 失败：

```text
raise
```

不要悄悄：

```text
print error
then legacy
```

---

# 91. Release mode

可以 fallback，

但 UI/log 必须明确：

```text
V2 dynamics unavailable — legacy visualization active
```

---

# 92. MainWindow 还有重复错误 print

当前 Dynamics compile error log 存在重复打印。

顺手清理即可。

---

# 93. P0/P1 测试升级：当前很多测试“名字比内容强”

这次必须重点修测试质量。

---

# 94. `test_stable_track_seed_cross_process`

如果只在同一进程调用两次：

```text
不是 cross-process test
```

---

## 真正测试

用：

```python
subprocess
```

启动两个独立 Python process，

同一 file hash，

输出 seed，

assert 完全相等。

---

# 95. `test_geometry_control_renderer_morph`

不能只检查：

```text
GeometryControl values are bounded
```

必须检查：

```text
Renderer/geometry output changes
```

---

# 96. `test_seek_warmup`

不能只 assert：

```text
material exists
scene.time == target
```

---

## 至少还要：

- 无递归调用；
- particle count > 0（对有活跃音频 fixture）；
- RingLayer transient 不继承旧 state；
- EnergyCore 不继承旧 state；
- 两次 seek 同一点宏观 descriptor 一致。

---

# 97. 新增 recursion guard test

可 monkeypatch / instrument：

```text
seek_to call count
```

一次：

```python
scene.rebuild_to_time(120)
```

不应该 recursively 调 `seek_to()` 几十次。

---

# 98. 新增 viewport test

Seek / rebuild：

```text
720x1280
```

不能内部使用：

```text
1920x1080
```

---

# 99. 新增 full-runtime contract test

直接 inspect：

```python
signature(RingLayer.update)
```

或更好，真实 Scene update。

当前 bug 必须被 test 捕获。

---

# 100. 新增 cache semantic version test

测试：

```text
v4 cache
```

在：

```text
v5 runtime
```

被拒绝。

---

# 101. 新增 silence calibration test

这也是 blocker。

---

# 102. 新增 band share test

synthetic：

```text
bass raw power = 8
mid raw power  = 1
high raw power = 1
```

最终：

```text
bass share ~ 0.8
```

---

# 103. 新增 event causality test

未来：

```text
beat at 1.00 s
```

查询：

```text
0.95 s
```

不能触发 beat burst。

---

# 104. 新增 deterministic particle test

相同：

```text
track_seed
tick
event index
```

两次创建粒子：

```text
angle
speed
size
life
```

一致。

---

# 105. 新增 30/60 FPS particle statistics test

不一定要求逐粒子 bit-identical。

先比较：

```text
particle count
mean speed
mean radius
lifetime distribution
```

相同一段时间后差异小。

---

# 106. 串行/并行 raw-frame seam test 仍然需要

但先修 determinism 与 rebuild 再做。

---

# 107. 当前 Exporter 的宏观 Material timeline 已经共用

这一点通过。

现在 seam 的主要不确定来源会变成：

```text
particle RNG
transient warmup
renderer random
```

---

# 108. Round 4 推荐实施顺序

严格按：

---

## R4-0：让当前 main 重新可靠运行

1. 修 `RingLayer.update()` contract；
2. 跑完整 pytest；
3. 加 V2 Scene smoke test；
4. 不允许 runtime TypeError。

---

## R4-1：修时间/缓存 correctness

1. L3 query interpolation；
2. cache version bump；
3. metadata version 单一来源；
4. silent track calibration；
5. all-NaN calibration defensive handling。

---

## R4-2：修 Seek / rebuild

1. 消除 recursive seek warmup；
2. reset ring/core/envelopes；
3. 真实尺寸；
4. 单一 warmup ownership；
5. MainWindow / sequential / parallel 共用。

---

## R4-3：真正 Renderer closure

1. RingLayer 使用 GeometryControl；
2. harmonic shell；
3. generative structure；
4. transient lattice；
5. VisualDNA 降级为 prior。

---

## R4-4：修 frequency semantics

1. raw band power；
2. band share；
3. global ratios；
4. spectral tilt。

---

## R4-5：deterministic visual randomness

1. stable particle id；
2. particle emit；
3. Scene ambient emit；
4. defect mask；
5. renderer decorations。

---

## R4-6：event causality + dt aware

1. crossed-event API；
2. causal beat impulse；
3. Poisson emission rate；
4. 30/60 FPS test。

---

## R4-7：export seam verification

1. serial/parallel macro；
2. particle statistics；
3. raw image seam。

---

# 109. 推荐 commit 划分

```text
commit 1
fix(runtime): align Scene and RingLayer V2 update contract

commit 2
test(runtime): add full V2 Scene smoke gate

commit 3
fix(analysis): interpolate L3 window queries and bump cache semantics

commit 4
fix(calibration): handle silence and non-finite feature arrays

commit 5
fix(seek): rebuild transient scene without recursive seek detection

commit 6
refactor(export): centralize visual warmup ownership

commit 7
feat(visual): drive RingLayer from GeometryControl

commit 8
feat(renderer): morph harmonic shell and structure from material geometry

commit 9
fix(analysis): separate visual band drive from raw spectral power share

commit 10
feat(random): introduce stable particle IDs and deterministic simulation streams

commit 11
fix(events): make beat/onset triggering causal and timestep-aware

commit 12
test(export): verify seek and serial/parallel visual continuity
```

---

# 110. 哪些文件这轮必须真的改

至少应涉及：

```text
app/visual/ring_layer.py
app/visual/renderer.py
app/visual/scene.py
app/visual/particles.py

app/analysis/features.py
app/analysis/spectrum.py
app/analysis/extractor.py

app/dynamics/calibration.py
app/dynamics/context.py
app/dynamics/deterministic.py

app/export/video_exporter.py
app/core/constants.py

tests/...
```

---

# 111. 如果下一提交没改 `renderer.py`

基本可以直接判定：

```text
Geometry Closure 未完成
```

---

# 112. 如果下一提交没 bump cache version

可以直接判定：

```text
causal L3 migration 对旧用户不可靠
```

---

# 113. 如果还存在 `hash(path)` seed

当前 factory 已经修了，不要回归。

---

# 114. 如果产品代码继续大量 global random

可以直接判定：

```text
Deterministic rendering 未完成
```

---

# 115. 如果 `seek_to()` 仍自己设置 target time 再从过去调用 public update

可以直接判定：

```text
Seek rebuild architecture 仍有递归风险
```

---

# 116. Round 4 的自动化验收清单

```text
[ ] full pytest passes
[ ] Scene V2 one-frame smoke passes
[ ] RingLayer accepts and uses GeometryControl
[ ] L3 query at 4.5s interpolates
[ ] v4 cache rejected by new runtime
[ ] silent track activity == 0
[ ] all-NaN flux/onset does not crash
[ ] seek_to/rebuild has no nested recursion
[ ] rebuild uses caller viewport dimensions
[ ] repeated rebuild at same time is deterministic
[ ] raw band shares sum ≈ 1
[ ] global bass ratio uses raw share
[ ] pre-beat frame cannot see future beat
[ ] stable seed truly matches across processes
[ ] particle init random values repeat
[ ] Renderer geometry differs for crystal/fluid/plasma
[ ] serial/parallel material state equal
[ ] serial/parallel geometry descriptor equal
```

---

# 117. Round 4 的人工验收

## A. 运行稳定性

```text
[ ] 直接启动播放不崩
[ ] 切歌不崩
[ ] 快速 seek 不崩
[ ] 竖屏/横屏 seek 正常
[ ] serial export 正常
[ ] parallel export 正常
```

---

## B. 宏观形态

```text
[ ] Crystal 不只是粒子更慢
[ ] Fluid 不只是粒子旋转
[ ] Plasma 不只是粒子更乱
[ ] 主 ring / shell / lattice 本身会发生明显连续形变
```

---

## C. 记忆

```text
[ ] 强高潮后 defect 不瞬间归零
[ ] 恢复段落存在 annealing 感
```

---

## D. 时间正确性

```text
[ ] beat 不提前
[ ] section context 不偷看未来
[ ] seek 后没有上一位置残留
```

---

## E. 可复现性

```text
[ ] 同一段连续导出两次画面行为稳定
[ ] parallel segment boundary 不跳
```

---

# 118. 这轮暂时不做什么

继续禁止：

- 真正 Chladni PDE；
- Navier–Stokes；
- Skyrmion；
- 3D；
- GPU particle rewrite；
- 新 Phase；
- ML genre classifier；
- 新 GUI settings；
- 用户可调几十个 physics sliders。

---

# 119. 为什么仍然不做 Chladni？

因为当前已经有足够多 state：

```text
order
excitation
mobility
defect
phase weights
geometry control
```

如果这些尚未让现有 ring/shell 明显不同，

再加入 Chladni 只会多一个 preset。

---

# 120. Round 4 的目标不是“更多”

而是：

> **让现有信息真的到达画面。**

---

# 121. 当前完成度重新估计

基于本轮当前 `main`：

| 子系统 | 当前状态 |
|---|---|
| Causal L3 generation | ✅ 基本完成 |
| L3 query interpolation | ❌ 未完成 |
| Real L3 → VisualContext | ✅ |
| Real L3/L4 → Material | ✅ |
| RMS reference calibration | ✅ |
| Silence calibration | ❌ |
| Spectral contrast normalization | ✅ 基本完成 |
| Raw spectral band share | ❌ |
| Stable bundle seed | ✅ |
| Material trajectory integration | ✅ |
| Material interpolation | ✅ |
| Potential/curl gate split | ✅ |
| Plasma force participation | ✅ |
| True stochastic plasma | 🟡 名不副实 |
| Scene → RingLayer contract | ❌ **当前 runtime blocker** |
| GeometryControl → RingLayer | ❌ |
| GeometryControl → Renderer | ❌ |
| Renderer macro phase morph | ❌ |
| Deterministic particle RNG | ❌ |
| Deterministic renderer RNG | ❌ |
| Seek macro state | ✅ |
| Seek transient reset | 🟡 |
| Seek deterministic warmup | ❌ / 当前实现存在递归风险 |
| Parallel macro trajectory | ✅ |
| Parallel visual equivalence | ❌ |
| Cache semantic migration | ❌ |

---

# 122. 对当前代码最重要的判断

Round 3 不是白做。

恰恰相反：

```text
Analysis
→ Context
→ Material
→ Trajectory
→ Particle field
```

这一半已经逐渐靠谱了。

当前真正卡住的是：

```text
Trajectory
→ Geometry
→ Renderer
```

以及：

```text
Runtime lifecycle
→ Seek
→ Randomness
→ Export reproducibility
```

---

# 123. 所以下一步不能再继续改 Material 数学公式

除非测试显示 phase collapse。

否则不要继续：

```text
0.25 改 0.27
0.18 改 0.22
```

这种无穷调权重。

先让 Geometry 真用这些 state。

---

# 124. 视觉闭环完成后的第一阶段预期

哪怕没有新特效，

你应该已经能看到：

```text
ordered section:
    ring spacing regular
    shells locked
    lattice coherent

groove:
    shell twist
    angular shear
    circulation

high excitation:
    broken arcs
    coherence loss
    rough edges
    particle scattering

cooling:
    defects persist
    segments progressively reconnect
```

---

# 125. 这是判断 Round 4 是否成功的肉眼标准

如果仍然只是：

```text
同一个环
+
不同粒子
+
不同亮度
```

那么没有完成。

---

# 126. 最后给开发 Agent 的执行摘要

当前 `main` 已经实现了不少 Round 3 核心逻辑，但代码存在一个明确的运行时契约断裂：

```text
Scene.update()
    → RingLayer.update(material=..., geometry=...)
```

而当前 RingLayer 不接受这些参数。

因此第一步必须先让完整 runtime tests 真正通过。

随后不要继续新增 physics 模块，而要完成四件事：

### 1. Correctness

```text
L3 interpolation
cache version migration
silent calibration
raw band shares
causal events
```

### 2. Lifecycle

```text
non-recursive seek rebuild
correct viewport warmup
single warmup owner
```

### 3. Visual Closure

```text
GeometryControl
    → RingLayer
    → Harmonic Shell
    → Generative Structure
    → Transient Lattice
```

### 4. Reproducibility

```text
stable particle IDs
keyed deterministic RNG
dt-aware emission
serial/parallel equivalence
```

本轮最大的验收条件不是：

```text
“V2 state exists”
```

而是：

\[
\boxed{
\text{MaterialState}
\rightarrow
\text{GeometryControl}
\rightarrow
\text{Macro Geometry}
}
\]

必须真实成立。

---

# 127. 最终验收句

只有当以下表述与真实默认代码路径完全一致时，Round 4 才算完成：

> **Stormy-Pulse uses causal multiscale audio context to drive a precompiled history-dependent material trajectory. The material state controls not only particle forces but the geometry of the rings, harmonic shell and generative structures. Seeking rebuilds transient state without recursion or hidden resolution assumptions; stale pre-causal caches are invalidated; and simulation-relevant randomness is deterministic across playback and export paths.**

在此之前，不要宣称 V2 visual closure complete。
