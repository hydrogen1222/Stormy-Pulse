# Stormy-Pulse V2 Round 5：主体几何闭环、确定性随机系统与频谱语义收口计划

> **文档性质**：第五轮 GitHub 源码审计后的实施文档，可直接交给开发 Agent  
> **审计基线**：GitHub `main` 最新提交 `c277e72`  
> **提交标题**：`feat(v2): stabilize runtime, bump cache v5, fix non-recursive seek and integrate RingLayer geometry damage`  
> **前置文档**：
> - `STORMY_PULSE_V2_IMPLEMENTATION_BLUEPRINT.md`
> - `STORMY_PULSE_V2_ROUND2_INTEGRATION_PLAN.md`
> - `STORMY_PULSE_V2_ROUND3_CLOSE_THE_LOOP_PLAN.md`
> - `STORMY_PULSE_V2_ROUND4_STABILIZE_AND_RENDER_CLOSURE.md`
>
> **Round 5 核心目标**：
>
> 1. 不再重复修已经通过的 Round 4 项；
> 2. 把 MaterialState 从“已经能影响一部分 ring / harmonic shell”推进到“主体 generative geometry 真正连续相变”；
> 3. 把已有 stable seed / deterministic helper 真正接入粒子、Scene、Effects 与 Renderer；
> 4. 彻底分离 `band_drive` 与真实 `band_share`；
> 5. 消除 beat/onset 的未来 80 ms 抢拍；
> 6. 统一 Seek 与 Parallel Export 的 transient warmup 所有权；
> 7. 把当前大量“测试名字比测试内容更强”的地方变成真正行为测试。
>
> 本轮仍然**不做新物理特效库**。目标是把已有 V2 世界做完整，而不是继续横向长模块。

---

# 0. 当前最新提交的总体评价

`c277e72` 比上一轮可靠很多。

Round 4 的几个高风险问题已经真实修复：

```text
✅ RingLayer.update() 已接受 material / geometry
✅ cache version 已从 v4 bump 到 v5
✅ extractor metadata 改为使用统一 CACHE_VERSION
✅ all-NaN flux/onset calibration 已加强防御
✅ silent RMS normalization 已开始返回 0
✅ Scene seek warmup 已改为内部 non-recursive update path
✅ seek 已接受 viewport width/height
✅ MaterialStateSequence 已有插值
✅ stable track seed 已使用 BLAKE2
✅ Particle 已有 stable particle_id
✅ RingLayer 已开始读取 GeometryControl
```

所以本轮**禁止把这些已经通过的内容重新设计一遍**。

---

# 1. 但 V2 还没有完成“主体几何闭环”

当前已经出现了一些真正的 GeometryControl 消费：

## RingLayer

已经开始使用：

```text
circulation
fragmentation
defect_density
coherence
symmetry
roughness
```

## Renderer harmonic shell

已经开始使用：

```text
symmetry
coherence
roughness
```

这说明 Round 4 不再只是“参数接上但没用”。

这是好事。

---

# 2. 当前真正剩下的几何断点

但是：

```text
_draw_generative_structure()
```

仍主要按：

```text
dna.structure_type
    ↓
reactor
vortex
organic
pulse
```

四选一。

而：

```text
_draw_transient_lattice_layer()
```

也仍主要读取旧 audio drive / effects，

没有真正使用：

```text
MaterialState
GeometryControl
defect_density
fragmentation
coherence
```

因此当前视觉仍可能呈现：

> “主体还是原来的 VisualDNA 模板，只是 ring 和 harmonic shell 有了一些新形变。”

Round 5 的第一核心任务就是完成这最后一大段。

---

# 3. Round 5 完成定义

只有以下条件同时满足，才可以宣称：

> `V2 Geometry + Determinism Semantic Closure complete`

---

## 3.1 Generative Structure

同一个：

```text
structure_type = reactor
```

在人工注入的：

```text
Crystal-like
Fluid-like
Plasma-like
```

状态下，主体几何必须肉眼明显不同。

---

## 3.2 Transient Lattice

必须受到：

```text
defect_density
fragmentation
coherence
symmetry
```

至少其中 3 个控制。

---

## 3.3 Harmonic shell

不能只吃：

```text
symmetry / coherence / roughness
```

还应至少考虑：

```text
circulation
angular_lock
fragmentation
```

中的适用部分。

---

## 3.4 Determinism

同一：

```text
track
absolute time
render size
fps
```

重复运行两次，

simulation-relevant random 结果必须一致。

---

## 3.5 Spectral balance

`bass_ratio / mid_ratio / high_ratio` 不能继续从每频带独立归一化的动画 drive 推断。

---

## 3.6 Fast events

未来尚未发生的 beat/onset 不允许因为：

```text
±80 ms event lookup
```

提前触发。

---

## 3.7 Seek / Parallel Export

必须明确只有一个组件负责 transient visual warmup。

不能：

```text
Scene warmup
+
Exporter 再 warmup
```

双重恢复。

---

# 4. Round 4 已通过项：不要重复修改

---

## 4.1 Cache v5

当前 commit 已真实：

```python
CACHE_VERSION = "v5"
```

并且 extractor：

```python
cache_version=CACHE_VERSION
```

这一项通过。

---

## 4.2 L3 causal generation

当前默认 rolling window 已真正变为：

```text
[t-W, t]
```

并使用统一 1 Hz 时间轴。

这一项通过。

---

## 4.3 L3 query interpolation

当前 `get_window_stats_at_time()` 已经实现 fractional-time interpolation。

这一项通过。

---

## 4.4 Silence calibration

当前 RMS near-zero / silent reference 已开始返回：

```text
0.0
```

而不是退化成 0.5。

这一项通过基础修复。

---

## 4.5 Stable seed

当前 DynamicsBundle 的 track seed 已不再依赖：

```python
hash(path)
```

而是稳定 BLAKE2。

这一项通过。

---

## 4.6 Seek recursive warmup

当前已经引入：

```text
internal update path
detect_seek=False
```

避免 warmup 调 public update 时继续触发 recursive seek。

这一项通过结构性修复。

---

# 5. P0：完整跑测试，不允许只说“tests added”

这轮首先要求 Agent 真实执行：

```bash
uv run pytest
```

如果 GUI / 环境导致部分测试不可运行，

必须给出：

```text
完整命令
passed
failed
skipped
skip 原因
```

不能只报告：

> “All relevant tests pass.”

---

# 6. 当前 Round 4 tests 仍有“名字强于内容”的问题

例如：

```text
test_v4_cache_version_rejection
```

如果只检查：

```python
CACHE_VERSION == "v5"
metadata_v4 != CACHE_VERSION
```

这不等于：

> FeatureCacheManager 真的拒绝了旧 cache。

---

# 7. 必须改成行为测试

真实创建：

```text
temporary v4 cache
```

然后调用：

```python
FeatureCacheManager.load(...)
```

或对应 `_verify_cache()` public path。

必须得到：

```text
cache miss / reject
```

而不是仅比较两个字符串。

---

# 8. `test_non_recursive_seek_rebuild` 也要加强

如果它只检查：

```text
scene.time == target
material is not None
```

不能证明“没有递归”。

---

## 建议

instrument：

```text
seek_to invocation count
```

一次 public seek：

```python
scene.seek_to(120.0)
```

不得嵌套再次进入 public `seek_to()`。

---

# 9. `test_stable_particle_ids` 不等于 deterministic particles

Stable ID 只是必要条件。

还必须验证：

```text
angle
speed
size
life
hue
```

在相同事件 key 下是否一致。

当前还没有。

---

# 10. 第一主线：真正完成 Generative Structure 的 Material Morph

这是本轮最重要的视觉任务。

---

# 11. 不删除 reactor / vortex / organic / pulse

它们已经是 Stormy-Pulse 的 style vocabulary。

保留。

但重新定义：

```text
VisualDNA.structure_type
=
material 的“先天几何风格”

MaterialState
=
当前物态
```

---

# 12. `structure_type` 不能继续等价于“整首歌固定拓扑”

目标：

```text
Reactor × Crystal
Reactor × Fluid
Reactor × Plasma

Vortex × Crystal
Vortex × Fluid
Vortex × Plasma

...
```

都应具有不同形态。

---

# 13. 推荐统一构造一个 `GeometryModulation`

可以直接复用已有：

```text
GeometryControl
```

不需要再创建新 dataclass。

Renderer 内部只做局部映射。

---

# 14. Reactor 的连续 Material 映射

原 reactor basis 通常有：

```text
concentric / segmented / radial engineering feel
```

---

## Crystal-like Reactor

```text
segment spacing regular
rotation lock
arc length consistent
radial alignment high
gap count low
line phase coherent
```

---

## Fluid-like Reactor

用：

```text
circulation
```

让：

```text
outer rings rotate at differential angular velocity
segments shear
radial connectors curve
angular phase drifts continuously
```

但保持整体连续。

---

## Plasma-like Reactor

用：

```text
fragmentation
roughness
defect_density
```

增加：

```text
arc gaps
local angular displacement
broken continuity
rough edge
```

---

# 15. Vortex basis 的 Material 映射

Vortex 已天生 circulation 高，

但 MaterialState 仍应决定：

### Crystal

```text
vortex 被锁成高度对称 spiral lattice
```

### Fluid

```text
spiral twist 最大
连续 stream-line feel
```

### Plasma

```text
spiral coherence 下降
局部断裂/散射
```

---

# 16. Pulse basis

Crystal：

```text
radial spokes angular-lock
repeat angle regular
```

Fluid：

```text
spokes 随 circulation sweep
```

Plasma：

```text
spokes length/continuity fragmented
roughness ↑
```

---

# 17. Organic basis

Crystal：

```text
organic motif 被高 symmetry 约束
```

Fluid：

```text
smooth asymmetric deformation
```

Plasma：

```text
rough / fractured / partial disappearance
```

---

# 18. 不要写 12 套 Renderer

禁止：

```text
CrystalReactorRenderer
FluidReactorRenderer
PlasmaReactorRenderer
...
```

应该：

```text
base style
+
continuous geometry controls
```

---

# 19. 最好把核心几何计算从 QPainter 中提出来

例如：

```python
compute_reactor_geometry(...)
compute_vortex_geometry(...)
compute_pulse_geometry(...)
compute_organic_geometry(...)
```

返回 geometry descriptor。

---

# 20. Geometry Descriptor 可以包含

```text
points
radii
angles
segment spans
phase offsets
visibility weights
line strengths
```

---

# 21. 这样做的好处

### 测试

可以直接比较：

```text
Crystal descriptor
Fluid descriptor
Plasma descriptor
```

### GPU

未来 GLSL 可以复用这些参数语义。

### 调试

能区分：

> MaterialState 没变化

还是：

> Renderer mapping 太弱。

---

# 22. 第二主线：Transient Lattice 真正吃 Defect

这个层非常适合呈现：

```text
order / defect
```

---

# 23. 建议映射

### symmetry

控制：

```text
节点规则程度
格线方向锁定
```

### coherence

控制：

```text
连接线连续程度
```

### defect_density

控制：

```text
missing links
local phase slip
node offset
```

### fragmentation

控制：

```text
较大尺度缺口
```

### circulation

Fluid 时：

```text
lattice 发生 shear / bend
```

---

# 24. Defect 必须具有空间寿命

不要：

```python
if random() < defect:
    skip line
```

每帧重新抽。

---

# 25. 推荐 persistent deterministic defect mask

当前 RingLayer 已有 coarse epoch damage 思路。

可以抽象成：

```text
stable key
+
coarse time epoch
+
smooth transition
```

---

# 26. 当前 RingLayer damage 的不足

当前大致：

```text
每 0.25 s
重新算一个 binary broken flag
```

问题：

- 可能出现 4 Hz 的突然闪变；
- `broken_segments` 粒度更像“整条 ring broken / not broken”；
- 不是真正 segment-level damage；
- 没有明确 healing trajectory。

---

# 27. 推荐改成连续 damage strength

例如每个 ring / arc segment：

```python
damage_target ∈ [0,1]
damage_current += (target-current) * alpha
```

target 只在 coarse epoch 更新。

---

# 28. damage target 由什么决定

```text
fragmentation
defect_density
deterministic hash
```

---

# 29. healing

Material defect 下降时：

```text
damage_current
```

也缓慢下降。

这样才能产生：

> annealing / reconnecting

而不是随机开关。

---

# 30. 第三主线：Harmonic Shell 补齐剩余 GeometryControl

当前已使用：

```text
symmetry
coherence
roughness
```

下一步建议：

---

## angular_lock

控制：

```text
lobe orientation phase
```

高 lock：

```text
方向稳定
```

低：

```text
慢漂移
```

---

## circulation

控制：

```text
whole-shell angular phase drift
```

Fluid 高时更明显。

---

## fragmentation

不要直接删整个 shell。

可以：

```text
局部 amplitude attenuation
missing angular interval
```

---

# 31. 第四主线：真正接 Deterministic Random

当前已经有：

```text
stable track_seed
stable particle_id
app/dynamics/deterministic.py
```

但这三件事尚未形成完整链。

---

# 32. 当前产品代码仍大量使用 global random

至少涉及：

```text
ParticleSystem.emit()
ParticleSystem.emit_burst()
Scene ambient emission
Scene onset sparks
EffectState camera shake
Renderer atmosphere spikes
Renderer grain setup
```

---

# 33. 所以当前不能称 deterministic visualizer

现在只能说：

```text
macro MaterialTrajectory deterministic
```

而不是：

```text
full visual simulation deterministic
```

---

# 34. 不要使用共享 `random.Random(seed)` 作为终局方案

因为不同路径：

```text
实时
串行
并行
HUD on/off
不同 draw order
```

可能消耗不同数量随机数，

随后未来结果全部分叉。

---

# 35. 必须使用 stateless keyed random

已有：

```text
app/dynamics/deterministic.py
```

优先复用。

不要再发明第二个 random helper。

---

# 36. 推荐统一 key schema

```text
track_seed
stream_name / stream_id
simulation_tick
object_id
component_index
```

---

# 37. Particle initial random

例如：

```text
particle_angle
particle_speed
particle_size
particle_life
particle_hue
```

全部由：

```text
track_seed + particle_id + property
```

派生。

---

# 38. Beat burst

同一个 beat event：

```text
event_id
```

生成的 burst 粒子必须固定。

---

# 39. Event ID 怎么定义

不要依赖：

```text
当前 list index
```

最好使用：

```text
event frame index
```

或：

```text
quantized event time + type
```

如果已有 event arrays，

索引本身通常可稳定。

---

# 40. Ambient emission

不能只：

```python
if random() < p:
```

---

## 先修 rate

定义：

```text
lambda events / second
```

\[
p(dt)=1-e^{-\lambda dt}
\]

---

## 再修随机

```text
track_seed
simulation_tick
"ambient_emit"
```

---

# 41. Particle stable ID

当前已经有：

```text
next_particle_id
```

保留。

注意：

```text
clear()
```

目前会重置 ID。

---

# 42. 是否应该 clear 时重置 ID？

### 对完全重建场景

可以。

因为 deterministic warmup 从同一时间起点开始，

会得到同样 emission sequence。

### 对普通清理

需要明确语义。

如果只是粒子达到 max count 清理，

不能随便 ID 重置。

---

# 43. 建议区分

```python
clear(reset_ids: bool = False)
```

Scene full reset / deterministic rebuild：

```text
True
```

普通管理：

```text
False
```

---

# 44. Camera shake

当前 Effects 中如果直接：

```python
random.uniform(...)
```

也会破坏重复性。

---

# 45. 推荐

触发 transient 时：

```text
event_id
track_seed
```

决定：

```text
shake angle
shake amplitude variation
```

后续 envelope deterministic 衰减。

---

# 46. Renderer atmosphere spikes

当前每次 draw 如果重新 global random：

```text
同一个 frame 重绘两次
```

都不一样。

---

# 47. 改为 frame-keyed decoration

例如：

```text
render_tick
spike_index
track_seed
```

---

# 48. Grain

当前如果使用 temporary：

```python
random.seed(...)
save state
restore state
```

虽然局部能稳定，

但不推荐长期保留。

直接：

```text
deterministic_float
```

生成 grain points。

---

# 49. 第五主线：Event Causality

这是一个还没修的音画同步问题。

---

# 50. 当前 `get_events_near(time, window=0.08)`

是对称窗口。

意味着：

```text
event at 1.00s
```

在：

```text
0.92~1.00s
```

就可能已经返回。

---

# 51. 后果

视觉 beat / onset 可能：

```text
提前最多约 80ms
```

对音乐可视化是可感知的抢拍。

---

# 52. L3 density 不受这个问题影响

因为当前 L3 已经改 causal。

问题主要在：

```text
fast beat
fast onset
```

---

# 53. 新增 Event API

推荐：

```python
get_events_crossed(
    previous_time,
    current_time,
)
```

返回：

```text
previous_time < t_event <= current_time
```

---

# 54. Scene 的瞬时 burst 应使用 crossed events

而不是：

```text
current frame beat flag rising edge
```

---

# 55. 优点

### 不抢拍

事件只有时间真正跨过后才触发。

### FPS 更稳

30 FPS 也不会因为没有 frame 正好落在 ±window 中而漏/提前。

---

# 56. VisualContext 的 beat impulse

如果 MaterialState 需要平滑 beat 驱动，

使用最近已发生 beat 的 causal decay：

\[
I_b(t)
=
s_b
e^{-(t-t_b)/\tau_b}
\]

仅：

\[
t \ge t_b
\]

---

# 57. Onset 同理

Fast visuals：

```text
crossed event
```

Slow Material：

```text
onset envelope / transient density
```

---

# 58. 第六主线：Band Drive 与 Band Share 必须终于分开

这是从第一轮就存在、目前仍没真正修掉的语义问题。

---

# 59. 当前 `compute_band_energies_6()`

流程大致是：

```text
raw spectral power in each band
    ↓
each band independently normalized by its own max
    ↓
moving-min / punch processing
    ↓
return only processed drive
```

---

# 60. 然后 GlobalFeatureSet

又用：

```text
mean(bass_drive)
mean(mid_drive)
mean(high_drive)
```

去算：

```text
bass_ratio
mid_ratio
high_ratio
```

---

# 61. 这不是跨频段能量比例

因为每个频带已经被各自拉满。

---

# 62. 结果会影响

```text
VisualDNA.structure_type
global spectral warmth
palette bias
VisualContext.spectral_tilt
```

这仍然可能制造错误的 global style prior。

---

# 63. 正确结构

一次 STFT 后得到两条路径。

---

## A. Band Drive

```text
raw power
    ↓
per-band independent normalization
    ↓
punch / smoothing
```

用于：

```text
动画响应
```

---

## B. Band Share

同一原始 power：

\[
share_i(t)
=
\frac{P_i(t)}
{\sum_j P_j(t)+\epsilon}
\]

用于：

```text
频谱构成
```

---

# 64. 建议数据结构

不要硬把新字段塞进现有 30D vector。

可以在：

```python
FrameFeatureSequence
```

增加：

```python
band_shares: np.ndarray  # (N, 6)
```

---

# 65. 为什么不建议扩 30D

当前已有不少代码把：

```text
N_FEATURES=30
```

当稳定 layout。

为了 6 个 share 改成 36，

会扩大兼容修改。

单独数组更语义清晰。

---

# 66. `GlobalFeatureSet`

改：

```text
bass_ratio
mid_ratio
high_ratio
```

来自：

```text
mean raw shares
```

而不是 drives。

---

# 67. `VisualContext.spectral_tilt`

也从：

```text
high_drive / (bass_drive + high_drive)
```

改成：

```text
high_share / (bass_share + high_share)
```

或更完整的 6-band center-of-mass tilt。

---

# 68. 更推荐 6-band spectral tilt

设 6 band center：

```text
0,1,2,3,4,5
```

则：

\[
tilt =
\frac{
\sum_i i\,share_i
}{5}
\]

天然 `[0,1]`。

---

# 69. 这是 audio semantic schema 改动

当前 cache 已经是：

```text
v5
```

如果 Round 5 增加：

```text
band_shares
```

必须：

```python
CACHE_VERSION = "v6"
```

---

# 70. 不要继续保持 v5

因为：

```text
v5 cache
```

没有 band_shares。

Silent fallback：

```text
用 drive 冒充 share
```

是不允许的。

---

# 71. 第七主线：Seek / Parallel Export Warmup Ownership

当前 Scene 已经拥有内部大约 2s visual warmup。

Parallel exporter 仍拥有：

```text
5~8s preroll
```

并且：

```text
先 scene.seek_to(warmup_start)
再从 warmup_start 循环到 segment_start
```

---

# 72. 这会造成双重 warmup

功能上未必错，

但：

- 浪费；
- 状态协议不清晰；
- 未来 deterministic 比较更难；
- MainWindow / Exporter rebuild 行为不完全统一。

---

# 73. 必须选择一个 owner

推荐：

> **Scene owns transient rebuild.**

---

# 74. 推荐 API

```python
scene.rebuild_to_time(
    target_time,
    width,
    height,
    warmup_seconds=VISUAL_WARMUP_SECONDS,
)
```

---

# 75. 内部

```text
reset transient state
        ↓
start = max(0, target-warmup)
        ↓
fixed / ordered simulation
        ↓
target
```

---

# 76. MainWindow Seek

直接：

```python
scene.rebuild_to_time(
    position,
    widget.width(),
    widget.height(),
)
```

---

# 77. Parallel Export

直接：

```python
scene.rebuild_to_time(
    segment_start_time,
    width,
    height,
    warmup_seconds=parallel_preroll_seconds,
)
```

然后：

```text
从 segment_start 第一帧开始输出
```

---

# 78. 不再外部 for-loop preroll

否则 owner 仍不统一。

---

# 79. Sequential Export

从 0 开始，

无需 rebuild。

---

# 80. warmup length

继续根据：

```text
max particle lifetime
ring envelope
core envelope
effect decay
```

决定。

---

# 81. Scene 当前 fallback viewport

现在 seek 能记住：

```text
last width/height
```

并在未知时 fallback。

这已经比 1920×1080 硬编码好。

---

# 82. 但 MainWindow 最好显式传尺寸

避免：

```text
第一次 update 前就 seek
```

落到 fallback 1280×720。

---

# 83. 第八主线：Plasma “stochastic” 命名与真实机制

当前 `w_plasma` 已真正进入 field。

这是 Round 4 进展。

---

# 84. 但所谓 stochastic 项仍主要是 deterministic sin/cos spatial pattern

严格说：

```text
不是 stochastic process
```

---

# 85. 两种选择

## 简化

改名：

```text
plasma_wave_scattering
```

这完全可以。

---

## 更符合原设计

在 ParticleSystem 中加入：

```text
deterministic time-correlated stochastic kick
```

---

# 86. 推荐第二种

因为本轮本来就要把：

```text
particle_id + deterministic RNG
```

接通。

---

# 87. Noise 相关时间

建议：

```text
100~250 ms
```

不要每 1/60s 独立白噪声。

---

# 88. 实现思路

定义：

```text
noise_epoch = floor(time / tau_noise)
```

获取：

```text
direction(epoch)
direction(epoch+1)
```

然后：

```text
smooth interpolation
```

---

# 89. 振幅

由：

```text
w_plasma
excitation
defect_density
activity
```

控制。

---

# 90. Potential / Curl / Stochastic 三者最终职责

\[
F =
F_{\rm potential}
+
F_{\rm curl}
+
F_{\rm stochastic}
\]

---

## Potential

```text
tonal confidence
order
crystal weight
```

---

## Curl

```text
mobility
fluid weight
activity
```

---

## Stochastic

```text
plasma weight
excitation
defect
```

---

# 91. 第九主线：Renderer Random Determinism

这一部分经常被忽略。

即使粒子 deterministic，

如果 Renderer 每次 draw：

```python
random.random()
```

还是无法重复 raw frame。

---

# 92. Atmosphere spikes

改成：

```text
track_seed
render_tick
spike_index
```

---

# 93. Render tick

不要用：

```text
number of times paint() was called
```

因为窗口重绘次数不稳定。

用：

```text
quantized absolute time
```

例如：

```python
render_tick = round(time * 60)
```

---

# 94. Grain

可以：

```text
track_seed
grain_index
```

静态。

---

# 95. Defect masks

使用：

```text
track_seed
coarse material tick
segment_id
```

---

# 96. 第十主线：真正检测跨运行 Determinism

---

# 97. `test_stable_track_seed_cross_process`

必须真正使用：

```python
subprocess
```

两个独立解释器。

---

# 98. `test_particle_initialization_deterministic`

创建两个独立 ParticleSystem，

同一：

```text
seed
event key
```

发射，

比较：

```text
particle_id
angle
vx/vy
size
life
hue
```

---

# 99. `test_renderer_same_time_same_output`

如果 Qt offscreen 可用：

同一：

```text
scene
absolute time
size
```

渲染两次 raw image。

像素应完全一致或极小容差。

---

# 100. 不要让 wall clock 进入任何视觉随机 key

禁止：

```text
time.time()
perf_counter()
```

参与随机视觉。

---

# 101. 第十一主线：真正 Geometry Behavior Tests

---

# 102. 现在的测试不能只检查 GeometryControl 自己不一样

需要检查：

```text
GeometryControl
    ↓
Renderer output
```

---

# 103. 最佳方式：Geometry Descriptor

例如：

```python
desc = renderer.build_generative_geometry(
    dna,
    geometry,
    ...
)
```

---

# 104. 对人工状态

### Crystal

```text
symmetry=.95
coherence=.95
circulation=.05
fragmentation=.05
roughness=.05
angular_lock=.95
```

### Fluid

```text
symmetry=.5
coherence=.75
circulation=.95
fragmentation=.2
roughness=.25
angular_lock=.35
```

### Plasma

```text
symmetry=.15
coherence=.2
circulation=.45
fragmentation=.9
roughness=.9
angular_lock=.1
```

---

# 105. assert

至少：

```text
segment positions differ
warp differs
gap masks differ
roughness amplitude differs
```

---

# 106. 再加 continuity test

输入：

```text
geometry A
geometry B
```

中间线性状态：

```text
0.5
```

输出也应平滑位于两者之间。

避免隐藏 hard phase switch。

---

# 107. 第十二主线：Band Share Tests

synthetic STFT：

```text
bass power = 8
mid power = 1
high power = 1
```

应该：

```text
bass share ≈ 0.8
```

---

# 108. drive 不要求 0.8

因为 drive 是各 band 自己的动态响应。

测试需要明确这两个概念不同。

---

# 109. Global ratios

应满足：

```text
bass_ratio + mid_ratio + high_ratio ≈ 1
```

---

# 110. 第十三主线：Event Causality Tests

event：

```text
beat = 1.000s
```

---

## 查询 0.950s

```text
beat impulse = 0
no burst
```

---

## 从 0.983 → 1.016

```text
crossed beat exactly once
```

---

## 下一帧

不能重复触发同一个 beat。

---

# 111. 30 FPS / 60 FPS

同一 10s beat train：

```text
burst event count
```

必须相同。

---

# 112. 当前 Phase / Material 部分不需要大改

Round 5 不要继续 vibe：

```text
0.25 → 0.27
0.18 → 0.22
```

除非 trajectory debug 明确显示 phase collapse。

---

# 113. 推荐先做真实 trajectory diagnostics

脚本：

```text
scripts/plot_v2_trajectory.py
```

仍然值得补。

---

# 114. 输出

```text
activity
order
excitation
mobility
defect
w_c
w_f
w_p
symmetry
circulation
fragmentation
roughness
```

---

# 115. 多歌曲比较

只作为本地开发 corpus：

```text
piano
pop
rock
EDM
ambient
metal/noise-heavy
acoustic
```

不做 genre classifier。

---

# 116. Phase occupancy collapse 检查

若所有歌曲：

```text
w_fluid mean > .8
```

才调 prototype。

---

# 117. 否则不要继续改 Material model

现在更可能的瓶颈已经是：

```text
Renderer mapping
```

而不是 state 数学。

---

# 118. Round 5 推荐实施顺序

---

## R5-0 — Runtime/Test Gate

1. 完整 pytest；
2. 修测试中的行为验证；
3. 确认 `c277e72` 无基础 runtime crash。

---

## R5-1 — Generative Geometry Closure

1. Generative Structure 接 GeometryControl；
2. Transient Lattice 接 GeometryControl；
3. Harmonic Shell 补 angular_lock / circulation / fragmentation；
4. VisualDNA 只做 style prior。

---

## R5-2 — Persistent Defect Geometry

1. Ring binary broken 改成连续 damage；
2. segment-level deterministic mask；
3. healing interpolation。

---

## R5-3 — Spectral Balance Semantics

1. raw band power；
2. band share；
3. FrameFeatureSequence 加 band_shares；
4. Global ratios 改 raw share；
5. VisualContext spectral_tilt 改 raw share；
6. cache v6。

---

## R5-4 — Causal Fast Events

1. `get_events_crossed()`；
2. causal beat impulse；
3. onset same；
4. Scene burst 改 crossed events。

---

## R5-5 — Deterministic Simulation RNG

1. Particle init；
2. ambient emission；
3. onset sparks；
4. plasma kick；
5. camera shake。

---

## R5-6 — Deterministic Renderer RNG

1. atmosphere；
2. grain；
3. decorative jitter；
4. frame-time keyed。

---

## R5-7 — Warmup Ownership

1. Scene `rebuild_to_time()`；
2. MainWindow 显式尺寸；
3. Parallel exporter 不再二次 preroll；
4. one source of truth。

---

## R5-8 — Reproducibility Tests

1. cross-process seed；
2. deterministic particles；
3. event count FPS；
4. repeated seek；
5. serial/parallel geometry；
6. raw-frame seam。

---

# 119. 推荐 commit 划分

```text
commit 1
test(v2): strengthen runtime, cache, seek and geometry behavior tests

commit 2
feat(renderer): morph generative structures from GeometryControl

commit 3
feat(renderer): couple transient lattice and harmonic shell to material geometry

commit 4
feat(geometry): make defect damage persistent and segment-level

commit 5
feat(analysis): separate band drive from raw spectral band share

commit 6
chore(cache): bump audio cache to v6 for band-share schema

commit 7
fix(events): make beat and onset triggering strictly causal

commit 8
feat(random): route particle and scene randomness through deterministic keyed streams

commit 9
feat(random): make renderer decorations deterministic at absolute time

commit 10
refactor(seek): centralize transient warmup in Scene.rebuild_to_time

commit 11
test(export): verify fps, seek and serial-parallel reproducibility
```

---

# 120. 哪些文件下一轮必须真正修改

至少预计：

```text
app/visual/renderer.py
app/visual/ring_layer.py
app/visual/particles.py
app/visual/scene.py
app/visual/effects.py

app/analysis/spectrum.py
app/analysis/features.py
app/analysis/extractor.py

app/dynamics/context.py
app/dynamics/deterministic.py

app/export/video_exporter.py
app/ui/main_window.py
app/config/constants.py

tests/...
```

---

# 121. 如果下一轮 `renderer.py` 只改几行 harmonic shell

则：

```text
主体 Geometry Closure 仍未完成
```

---

# 122. 如果下一轮只增加 `particle_id`

当前已经有了。

不能再把：

```text
stable ID
```

当作：

```text
deterministic particles
```

---

# 123. 如果产品代码还大量 global random

则不能宣告：

```text
deterministic rendering complete
```

---

# 124. 如果 `get_events_near(... ±80ms)` 仍用于 fast beat trigger

则不能宣告：

```text
audio event timing causal
```

---

# 125. 如果 global bass/mid/high 仍来自 band_drive mean

则不能宣告：

```text
spectral balance semantics fixed
```

---

# 126. 如果加入 band_shares 却不 bump v6

则旧 v5 cache 会缺字段。

不能 silent fallback。

---

# 127. 如果 Parallel Exporter 仍手写 preroll loop，而 Scene 同时 internal warmup

则 warmup ownership 仍未收口。

---

# 128. Round 5 自动测试最低清单

```text
[ ] uv run pytest full suite passes
[ ] actual v4/v5 stale cache rejection behavior tested
[ ] geometry descriptor differs crystal/fluid/plasma
[ ] geometry morph continuity tested
[ ] transient lattice responds to defect
[ ] ring damage persists instead of 4Hz binary flicker
[ ] raw band shares sum to one
[ ] synthetic bass-dominant share behaves correctly
[ ] global b/m/h ratios use raw share
[ ] spectral_tilt uses raw share
[ ] future beat cannot fire early
[ ] crossed beat fires exactly once
[ ] 30/60fps beat burst counts equal
[ ] stable seed equal in independent processes
[ ] particle init deterministic
[ ] camera shake deterministic
[ ] renderer atmosphere deterministic
[ ] repeated seek same time produces same geometry/particle stats
[ ] parallel/serial material and geometry equal
[ ] no double warmup path
```

---

# 129. 人工视觉验收

---

## 同一 Reactor 风格

必须能肉眼看到：

```text
Crystal Reactor
≠
Fluid Reactor
≠
Plasma Reactor
```

而不是只看粒子区别。

---

## 同一首歌

必须看到：

```text
intro
→ groove
→ climax
→ recovery
```

主体 structure 发生连续 morph。

---

## Defect

高潮后的缺陷：

```text
不能 0.25s 一闪一闪
```

而应：

```text
出现
积累
持续
逐渐愈合
```

---

## Beat

不能有明显视觉提前。

---

## Seek

同一位置反复 seek：

```text
宏观结构稳定
粒子统计稳定
装饰随机稳定
```

---

## Parallel Export

segment boundary：

```text
不能突然换一套随机宇宙
```

---

# 130. 性能要求

Geometry closure 不应通过：

```text
每像素复杂 Python
```

实现。

---

# 131. Renderer 仍以现有 path/curve primitive 为主

MaterialState 只调：

```text
参数
顶点
mask
phase
```

---

# 132. deterministic hash 不要在每个 pixel 调

只用于：

```text
particle
segment
spike
defect cell
```

---

# 133. Band share 计算应复用已有 STFT

不要为了 share 再做一遍 STFT。

---

# 134. Event causal lookup 用 searchsorted

不要每 frame 全数组扫描。

---

# 135. Deterministic helper 应 centralize

不要：

```text
RingLayer 手写 XOR
Particle 用 BLAKE
Renderer 用 random.Random
Effects 又另一套
```

---

# 136. 建议为 deterministic.py 增明确 API

例如：

```python
rand01(seed, stream, tick, object_id, component=0)
rand_signed(...)
rand_range(...)
angle(...)
```

但不要发展成巨大 RNG framework。

---

# 137. RingLayer 当前 XOR mask 应迁移到统一 deterministic helper

不是因为 XOR 必然错，

而是避免：

```text
每个模块一套随机规则
```

后面无法测试/维护。

---

# 138. 串并行可复现的最终关键

不是：

```text
所有 worker 调 random.seed(same_seed)
```

而是：

> 同一事件/对象的随机值由它自己的稳定 key 决定。

---

# 139. 为什么这很重要

Parallel worker 从不同时间起点 warmup，

消耗 RNG 的数量本来就不同。

stateful RNG 很容易导致未来分叉。

---

# 140. Render-only randomness 也不能消耗 simulation stream

必须彻底分离。

---

# 141. 推荐 stream names

```text
particle_spawn
particle_speed
particle_size
particle_life
particle_hue

ambient_emit
onset_spark
beat_burst

camera_shake

ring_damage
lattice_damage

atmosphere_spike
grain
```

---

# 142. 不必担心字符串 hashing 性能

可以 deterministic helper 内：

```text
固定映射 stream name -> uint64
```

或 BLAKE 小数据。

这些对象数远低于像素数。

---

# 143. Round 5 仍不做真正 Chladni

理由没有变化：

现在已有足够多 geometry controls。

必须先证明它们能让主体世界显著不同。

---

# 144. 仍不做 GPU 大迁移

当前 CPU/QPainter 是最适合验证语义的参考实现。

未来 GPU 必须复刻：

```text
同一个 MaterialState / GeometryControl
```

而不是另造视觉逻辑。

---

# 145. 仍不新增 Phase

当前 state：

```text
order
excitation
mobility
defect
```

足够。

---

# 146. 如果同质化仍严重

先排查：

```text
Material trajectory dynamic range
GeometryControl dynamic range
Renderer mapping gain
VisualDNA prior strength
random texture dominance
smoothing depth
```

---

# 147. 不要通过更多随机噪声“制造差异”

随机 != 结构差异。

目标是：

```text
history-driven structural difference
```

---

# 148. Round 5 完成后的理想架构

```text
Audio Analysis
    │
    ├── L1 instantaneous drive
    ├── L2 causal events
    ├── L3 causal context
    ├── L4 structure
    └── raw spectral shares
    │
    ▼
VisualContext
    │
    ▼
MaterialTrajectory
    │
    ├───────────────┬─────────────────┐
    ▼               ▼                 ▼
Potential/Curl   GeometryControl   Fast Event Modulation
    │               │                 │
    ▼               ▼                 ▼
Particles       Ring / Shell /     Burst / Crack /
+ stochastic    Structure/Lattice  Ripple
    │               │                 │
    └───────────────┴─────────────────┘
                    │
                    ▼
            Deterministic Frame
```

---

# 149. Round 5 的真正里程碑

此前：

```text
V2 MaterialState exists
```

Round 4：

```text
V2 MaterialState begins to affect ring/shell
```

Round 5 目标：

```text
V2 MaterialState defines the full visual world's structure
```

---

# 150. 给开发 Agent 的最终执行摘要

从 `c277e72` 继续开发。

不要重写已完成的：

```text
causal L3
cache v5 migration
RMS silence fix
BLAKE2 track seed
Material interpolation
non-recursive seek
RingLayer API contract
```

本轮集中做以下事情：

### 第一优先级

```text
GeometryControl
    ↓
Generative Structure
Transient Lattice
Harmonic Shell
```

让主体世界真正发生 Crystal / Fluid / Plasma 的连续结构变形。

### 第二优先级

使用现有 deterministic helper，把：

```text
Particle
Scene
Effects
Renderer
```

的 simulation-relevant random 全部改为 keyed deterministic randomness。

### 第三优先级

把：

```text
band_drive
```

与：

```text
raw band_share
```

彻底分开，

并将 cache 升级到 v6。

### 第四优先级

fast beat/onset 改为严格 causal crossed-event semantics。

### 第五优先级

统一：

```text
Scene rebuild
MainWindow seek
Parallel Export preroll
```

的 warmup ownership。

---

# 151. 最终验收句

只有下面这句话已经能准确描述默认代码路径时，Round 5 才算完成：

> **Stormy-Pulse uses the history-dependent material trajectory to continuously morph its generative structures, harmonic shells and lattice geometry—not only particle motion. Spectral balance is derived from true cross-band power shares, beat/onset events are causal, and all simulation-relevant randomness is keyed deterministically so playback, seeking and parallel export reconstruct the same visual world at the same absolute time.**

如果：

```text
generative structure 仍只看 structure_type
```

或者：

```text
particles / renderer 仍大量 global random
```

或者：

```text
bass_ratio 仍来自 independently normalized drive
```

那么 Round 5 仍未完成。
