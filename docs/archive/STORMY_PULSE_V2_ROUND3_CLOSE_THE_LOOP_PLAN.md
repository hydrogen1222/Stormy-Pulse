# Stormy-Pulse V2 Round 3：闭环集成、真实多尺度语义、确定性与几何相变实施计划

> **文档性质**：第三轮源码验收后的实施计划，可直接交给开发 Agent 执行  
> **审计基线**：GitHub `main`，提交 `cfaff45d04ee8e8aac000ac90da5f06d838cf730`  
> **提交标题**：`feat(dynamics): integrate V2 DynamicsBundle into MainWindow, Scene, ParticleSystem, Seek and VideoExporter`  
> **前置文档**：
> - `STORMY_PULSE_V2_IMPLEMENTATION_BLUEPRINT.md`
> - `STORMY_PULSE_V2_ROUND2_INTEGRATION_PLAN.md`
>
> **本轮主题**：`Close the Loop`。  
> Round 2 已经让 V2 MaterialTrajectory 真正进入部分运行链路；Round 3 不再允许“再搭一层”，而要完成从 **分析语义 → MaterialTrajectory → Field → Particle → Geometry → Renderer → Seek/Export** 的完整闭环。

---

# 0. 先给结论：`cfaff45` 做到了什么，没有做到什么

这次提交比上一轮有明显实质进展。

已经真实发生：

```text
MainWindow
    ↓
TrackCalibration
    ↓
VisualContextBuilder
    ↓
MaterialTrajectoryCompiler
    ↓
DynamicsBundle
    ↓
Scene.set_dynamics_bundle()
```

并且：

```text
Scene
    ↓
MaterialState(t)
    ↓
AnalyticalPESField
    ↓
ParticleSystem
```

也已经成为 V2 bundle 存在时的运行路径。

串行和并行 VideoExporter 也会分别编译 V2 dynamics bundle。

Seek 也开始调用：

```python
scene.seek_to(position)
```

因此这一轮不能再说：

> “V2 只是 test-only dead code。”

这部分已经迈过去了。

---

但是，当前还**没有完成 V2 闭环**。

最关键的事实：

```text
cfaff45 changed files
```

里面没有：

```text
app/visual/renderer.py
app/visual/ring_layer.py
app/analysis/window.py
app/analysis/spectrum.py
app/analysis/extractor.py
app/dynamics/deterministic.py
```

其中：

- `renderer.py / ring_layer.py` 是“宏观几何相变”真正落地的位置；
- `window.py` 是 L3 causal semantics 的核心；
- `spectrum.py / extractor.py` 是 spectral contrast 与 band share 老问题所在；
- `deterministic.py` 是跨运行一致性真正落地的位置。

所以当前最准确的状态是：

> **V2 已接入宏观状态查询和粒子场，但宏观几何、真正多尺度音频语义、随机确定性与完整 Seek/Export 重建仍未完成。**

---

# 1. 本轮最高规则

本轮禁止再新增新的“平行 V3 架构”。

不要新增：

```text
MaterialEngineV3
AdvancedPES2
RendererPhysicsV2
NewPhaseController
PhysicsBridge2
```

除非现有设计在实测中证明无法工作。

本轮的核心操作必须是：

```text
修已有数据语义
        ↓
让已有 V2 状态真正进入已有 Renderer
        ↓
替换旧随机性
        ↓
完成 Seek/Export 状态重建
        ↓
写能够真正失败的集成测试
```

---

# 2. Round 3 完成定义

只有同时满足以下要求，才能声称：

> `Stormy-Pulse V2 core integration complete`

---

## 2.1 音频语义完整

必须完成：

- L3 trailing causal windows；
- 2/4/8 s 统一时间轴；
- L3 查询插值；
- 真正 `transient_density`；
- 真正 `beat_density`；
- spectral contrast 的正确尺度；
- raw spectral band share；
- `section_progress` 真实；
- novelty/boundary/climax 有明确时间语义。

---

## 2.2 MaterialState 真正吃到多尺度语义

不能只是 VisualContext 有字段。

MaterialState 至少应真实使用：

```text
energy_slow
energy_trend
transient_density
beat_density
novelty / boundary_impulse 中至少一个
```

否则 L3/L4 依然只是“漂亮数据结构”。

---

## 2.3 Renderer 真正读取 GeometryControl

至少：

```text
symmetry
coherence
circulation
fragmentation
roughness
angular_lock
```

中的多数必须改变主体几何。

---

## 2.4 V2 主运行路径不再把 `phase_state=None` 传给 RingLayer

当前 V2 active 时：

```text
current_material_state = MaterialState
```

但：

```text
ring_layer.update(... phase_state=self.phase_state)
```

仍然传旧 legacy `phase_state`。

这是必须修掉的断点。

---

## 2.5 Determinism 真正进入产品

必须满足：

```text
同一歌曲
同一时间
同一 fps
```

重复导出获得一致的宏观与粒子初始随机结果。

并行 worker 不允许因为 Python hash randomization 得到不同 seed。

---

## 2.6 Seek 真的重建视觉世界

`scene.seek_to()` 不能只：

```text
清 particles
清 effects
查询 material
```

还必须处理：

```text
RingLayer
EnergyCore
short envelopes
particle warmup
event state
```

---

## 2.7 30 / 60 FPS 不改变宏观 MaterialTrajectory

这点已经基本具备。

但粒子与 stochastic events 仍需固定步长/时间尺度处理。

---

# 3. 当前 V2 主链路：哪些地方已经验收通过

---

## 3.1 MainWindow 已真实创建 V2 DynamicsBundle

当前在 analysis finished 后会：

```python
TrackCalibration.compute(...)
VisualContextBuilder(...)
MaterialTrajectoryCompiler.compile(...)
DynamicsBundle(...)
scene.set_dynamics_bundle(...)
```

这是正确方向。

保留。

---

## 3.2 Scene 已开始查询预编译 MaterialState

V2 bundle 存在时：

```python
ctx = context_builder.at(time)
mat = material_trajectory.get_state_at_time(time)
analytical_field.update(ctx, mat)
```

并把：

```text
material
AnalyticalPESField
```

传给 ParticleSystem。

这一部分属于真实产品接线，不要回退。

---

## 3.3 Legacy PhaseEngine 已经变成 fallback

当前：

```python
if self.dynamics_bundle is None:
    legacy phase
    legacy PES
```

V2 bundle 正常时不会调用旧 PhaseEngine。

已有测试也 monkeypatch legacy engine 强制抛错，验证 V2 Scene 可继续更新。

这个测试方向是正确的。

---

## 3.4 Sequential / Parallel Export 已开始编译同一 V2 宏观轨迹

这也是真进展。

因此长期 Material memory 已经不依赖 export preroll 恢复。

Preroll 现在理论上只需要恢复：

```text
particles
effects
ring/core short state
```

这正是我们希望的方向。

---

## 3.5 RMS calibration reference bug 已修

`TrackCalibration` 现在保存：

```text
rms_reference
```

并默认用同一 reference 做 normalization。

这一修复正确。

---

## 3.6 Analytical gradient test 已经变成真正 numerical comparison

这次：

```python
np.testing.assert_allclose(...)
```

确实出现了。

比上一轮只检查 NaN 的测试可靠很多。

---

# 4. 当前最大断点：Renderer 完全没有接 MaterialState / GeometryControl

这是 Round 3 的第一优先级。

---

## 4.1 当前事实

`MaterialState` 已经提供：

```python
state.geometry_control
```

其中：

```text
symmetry
coherence
circulation
fragmentation
roughness
angular_lock
```

但是当前 `renderer.py`：

```text
没有 geometry_control
没有 current_material_state
没有 w_crystalline
没有 fragmentation
没有 circulation
没有 defect
```

这意味着：

> MaterialState 已经存在，但主体视觉几何基本不知道它存在。

---

## 4.2 当前实际视觉变化主要来自粒子

V2 active：

```text
MaterialState
  ↓
AnalyticalPES
  ↓
Particle motion
```

但是：

```text
harmonic shell
generative structure
main ring
transient lattice
background topology
```

仍然走旧 VisualDNA / audio-drive 逻辑。

因此当前“反同质化”效果很可能仍有限。

---

# 5. 必须完成 GeometryControl → Renderer 闭环

本轮必须明确建立：

```text
MaterialState
    ↓
GeometryControl
    ↓
RingLayer / Renderer
```

---

## 5.1 Scene 中保存当前 GeometryControl

V2 active 时：

```python
self.current_material_state = mat
self.current_geometry_control = mat.geometry_control
```

reset/seek 时都更新。

---

## 5.2 Renderer 获取方式

推荐：

```python
material = self.scene.current_material_state
geometry = self.scene.current_geometry_control
```

不要再传几十个 positional args。

---

# 6. RingLayer API 应改

当前：

```python
ring_layer.update(... phase_state=self.phase_state)
```

V2 下这个值通常不是新 MaterialState。

应改成：

```python
ring_layer.update(
    ...,
    material=material,
    geometry=geometry,
)
```

legacy fallback 可以在 Scene 中映射成一个兼容 GeometryControl。

最终 RingLayer 不需要知道：

```text
旧 PhaseState class
```

---

# 7. GeometryControl 第一版不需要重新画整个 Renderer

不要大爆改。

先让现有几何受到以下六个连续调制。

---

## 7.1 `symmetry`

控制：

```text
角向 mode 的整数锁定
重复结构的均匀程度
左右/旋转对称
ring segment spacing
```

高：

```text
规则、重复、晶体感
```

低：

```text
不规则、局部偏移
```

---

## 7.2 `coherence`

控制：

```text
相邻曲线 phase 一致性
line continuity
局部 jitter 的相关长度
```

高：

```text
完整连续
```

低：

```text
曲线之间逐渐失配
```

---

## 7.3 `circulation`

控制：

```text
angular warp
spiral offset
vortex twist
curve advection
```

这是 Fluid 的核心宏观表现。

---

## 7.4 `fragmentation`

控制：

```text
broken arc
segment gap
local split
断裂概率
```

必须尽量具有寿命/记忆，而不是每帧随机。

---

## 7.5 `roughness`

控制：

```text
高频局部表面扰动
边缘不稳定
plasma-like texture
```

不要简单映射成“随机抖动很多”。

需要时间连续。

---

## 7.6 `angular_lock`

控制：

```text
稳定 nodal direction
固定 Fourier angle
chroma field 对 shell 的锁相程度
```

---

# 8. Geometry 变化必须是连续 morph

禁止：

```python
if phase_name == "crystalline":
    draw_crystal()

elif phase_name == "hydrodynamic":
    draw_fluid()

else:
    draw_plasma()
```

必须：

```text
geometry parameter
=
w_c * crystal_preference
+
w_f * fluid_preference
+
w_p * plasma_preference
```

或直接从 MaterialState 连续推导。

---

# 9. VisualDNA 本轮必须真正降级为弱 prior

旧：

```text
structure_type = reactor/vortex/organic/pulse
```

仍可以保留。

但是建议限制影响权重。

概念：

```text
FinalGeometry
=
0.2~0.35 * StylePrior
+
0.65~0.8 * CurrentMaterialState
```

不要让：

```text
structure_type="reactor"
```

导致整首歌始终像 Reactor。

---

# 10. 当前 `phase_state` 在 V2 下应废弃

建议：

```text
self.phase_state
```

仅 legacy fallback 使用。

V2 Renderer/RingLayer 禁止读取。

新的调试 phase 名称：

```python
self.current_material_state.phase_name
```

---

# 11. 第二个大问题：L3 注释写“Causal”，实际 window.py 完全没改

这是必须纠正的“代码事实与注释不一致”。

---

## 11.1 当前 window.py 仍是 forward-looking

当前逻辑：

```python
start = i * hop_frames
end = start + window_frames
```

所以：

```text
t = 20 s
8 s window
```

描述：

```text
20 ~ 28 s
```

不是：

```text
12 ~ 20 s
```

---

## 11.2 VisualContext 注释：

```text
# L3 Window Stats (Causal Trailing Windows)
```

目前是错误注释。

在 window.py 真修之前，禁止保留这句。

---

# 12. Round 3 必须重写 L3 生成语义

统一定义时间轴：

```python
times_1hz = np.arange(
    0.0,
    duration + small_eps,
    1.0
)
```

对每个：

```text
t
```

和窗口：

```text
W = 2,4,8
```

定义：

\[
[t-W,\; t]
\]

并裁剪到：

\[
[0,t]
\]

---

# 13. 2/4/8s 数组长度必须完全相同

必须保证：

```python
len(stats_2s[key])
==
len(stats_4s[key])
==
len(stats_8s[key])
==
len(times_1hz)
```

不再：

```text
min_len 截断
```

---

# 14. Event density 也必须 trailing causal

当前：

```text
[start, start+window]
```

应改：

```text
[t-window, t]
```

---

# 15. Event density 可顺手用 searchsorted 优化

当前每个窗口：

```python
np.sum((events >= start) & (events < end))
```

是 O(Nevents × Ntimestamps)。

推荐：

```python
left = np.searchsorted(events, start, side="left")
right = np.searchsorted(events, end, side="right")
count = right-left
```

尤其 MaterialTrajectory 每首歌还会高频查询 context。

---

# 16. FeatureCache.get_window_stats_at_time() 必须插值

当前：

```python
idx = int(time)
```

应该改为：

```python
i0, i1, u
```

然后：

```python
(1-u) * value[i0] + u * value[i1]
```

---

# 17. VisualContext 不要自己重复写窗口索引

当前直接：

```python
idx = int(np.clip(time, ...))
```

这是重复逻辑。

应该：

```python
stats2 = cache.get_window_stats_at_time(time, 2)
stats4 = cache.get_window_stats_at_time(time, 4)
stats8 = cache.get_window_stats_at_time(time, 8)
```

统一语义。

---

# 18. `transient_density` 现在仍是假值

当前初始化：

```python
transient_density = onset_norm * 0.8
```

即使 L3 存在，也没有覆盖。

所以本轮必须：

```python
transient_density =
    stats4["transient_density"]
```

或短/中窗口混合：

```python
0.65 * stats2
+
0.35 * stats4
```

---

# 19. `beat_density` 现在也不是 beat density

当前：

```python
beat_density = beat_impulse * beat_conf
```

这只是：

> 当前是不是接近一个 beat。

不是：

> 最近几秒节拍密度。

本轮必须：

```python
beat_density =
    stats4["beat_density"]
    * beat_confidence
```

可适当加入 2s。

---

# 20. Fast Beat 与 Slow Beat Density 必须分开

保留：

```text
beat_impulse
```

用于瞬时 hit。

同时：

```text
beat_density
```

用于 groove / mobility。

两者不能互相冒充。

---

# 21. `energy_trend` 当前实现也不理想

当前：

```python
(e2 - e8) * 2
```

这表示：

> 短时能量相对于长时背景高多少。

它更接近：

```text
energy_deviation
```

不完全是 trend。

可以两种方案。

---

## 21.1 方案 A：真正使用 L3 自带 `energy_trend`

推荐。

定义：

```text
2s trend
4s trend
8s trend
```

VisualContext 用：

```python
energy_trend =
    weighted_signed_normalize(stats4["energy_trend"])
```

---

## 21.2 方案 B

若保留：

```text
e2-e8
```

则改名：

```text
energy_deviation
```

不要叫 trend。

---

# 22. MaterialState 目前没有用 `energy_slow`

`MaterialStateEngine.update()` 现在 excitation 主要使用：

```text
energy_fast
flux
onset
transient_density
```

`energy_slow` 没进来。

---

## 本轮建议

例如：

```python
exc_target = (
    0.27 * energy_fast
    + 0.13 * energy_slow
    + 0.22 * flux
    + 0.18 * onset
    + 0.20 * transient_density
)
```

这里只是初始建议权重。

需要 real track calibration。

---

# 23. MaterialState 也没有使用真正 L4

当前：

```text
novelty
boundary_impulse
climax_prior
section_progress
```

都没有实际进入 dynamics。

这意味着 L4 虽然 VisualContext 已填充，但对 MaterialTrajectory 没影响。

---

# 24. L4 正确用途：调“易感性”，不是直接改 phase

推荐：

```python
susceptibility = 1.0 \
    + 0.20 * novelty \
    + 0.15 * boundary_impulse
```

然后：

```text
defect creation
topology rearrangement
```

在段落边界附近稍微更容易。

---

# 25. Climax 只能是弱 prior

例如：

```python
exc_target += 0.05 * climax_prior * energy_fast
```

或：

```python
damage_rate *= 1.0 + 0.10 * climax_prior
```

不要：

```python
if climax:
    plasma
```

---

# 26. `section_progress` 不一定非要进 MaterialEngine

它可以主要用于 Renderer：

- section 初期结构重建；
- section 中期稳定；
- section 尾部逐渐增加结构 susceptibility。

但第一轮不要复杂。

---

# 27. 当前 boundary impulse 仍带 future anticipation

现在：

```python
min(
    abs(time-sec_start),
    abs(time-sec_end)
)
```

意味着在下一段真正开始前：

```text
画面已经感觉到未来 sec_end
```

如果我们坚持 causal：

```python
elapsed = time - sec_start
boundary_impulse = exp(-elapsed/tau)
```

只对刚发生的 boundary 响应。

---

## 若确实想视觉提前预热

请明确拆成：

```text
boundary_impulse       # causal
boundary_proximity     # optional look-ahead
```

不要同一个变量语义混合。

---

# 28. Novelty curve 最好保存真实时间轴

`section.py` 里：

```text
struct_hop = sr
```

所以大约 1 秒一个 novelty sample。

目前 VisualContext 用：

```python
time * len(curve)/duration
```

近似映射。

建议 `SectionFeatureSet` 增：

```text
novelty_times
```

或者至少在 section 模块明确：

```python
novelty_frame_rate = sr / struct_hop
```

然后按真实频率查询。

---

# 29. 第三个老问题：spectral contrast 仍完全没修

这是当前最明确的未完成 P0。

---

## 29.1 当前仍然：

```python
global_contrast = np.mean(spectral_contrast_vec)
```

然后：

```python
global_contrast > 0.4
global_contrast > 0.45
line_thickness = 1.2 + global_contrast * 4
```

librosa spectral contrast 不是 `[0,1]`。

所以逻辑仍然饱和。

---

# 30. TrackCalibration 虽然新增 normalize_contrast，但运行中没真正用

MainWindow / exporter 创建 calibration 时只传：

```text
RMS
flux
onset
```

没有传：

```text
contrast_arr
```

更重要的是：

当前 `compute_spectral_contrast()` 返回的是：

```text
7 个频带的全曲均值
```

而不是时间序列。

所以 TrackCalibration 也不能直接把它当 frame-wise contrast。

---

# 31. 推荐重构 Spectral Contrast

更合理方案：

```python
contrast_matrix =
    librosa.feature.spectral_contrast(...)
```

保留：

```python
contrast_frame =
    mean(contrast_matrix, axis=0)
```

它才是随时间的 1D 序列。

---

## 31.1 Frame-level normalized contrast

利用整首歌：

```text
P10/P95
```

得到：

```text
contrast_norm(t)
```

---

## 31.2 Global contrast

再计算：

```python
global_contrast_norm =
    mean(contrast_norm(t))
```

这样：

```text
detail_style
line_thickness
theme saturation
```

都可以安全使用 `[0,1]`。

---

# 32. 是否要把 contrast 加入 30D L1？

推荐增加。

当前 30D 其实不是不可侵犯协议。

可升级：

```text
N_FEATURES = 31
F_CONTRAST = 30
```

然后：

```text
AUDIO_CACHE_VERSION bump
```

这比让 contrast 永远游离在 Global 层更干净。

---

# 33. 第四个老问题：band ratio 仍然是假比例

当前每个频带先：

```python
band /= band.max()
```

然后再：

```python
b_mean / (b_mean+m_mean+h_mean)
```

不是原始功率 share。

---

# 34. 推荐 `BandFeatures` 双轨语义

在 `spectrum.py` 同时计算：

```text
band_drive
band_power
band_share
```

---

## `band_drive`

现有逻辑可以保留：

```text
每频带独立归一化
moving-min subtraction
punch factor
```

用于视觉响应。

---

## `band_power`

原始：

```python
sum(S_power[bins])
```

---

## `band_share`

同一 frame：

\[
share_i =
P_i /
\sum P_j
\]

用于：

```text
global spectral balance
spectral tilt
VisualDNA prior
```

---

# 35. 不要用 drive 推断音色平衡

这是核心语义原则：

```text
drive = 动画强度
share = 光谱构成
```

---

# 36. Cache 必须 bump

如果：

- L3 时间语义改；
- L1 增 contrast；
- 新增 band_share；
- section novelty time axis 改；

必须：

```text
AUDIO_CACHE_VERSION += 1
```

旧 cache 不应 silent fallback。

---

# 37. 第五个关键问题：track_seed 当前是 Python `hash(path)`

当前：

```python
track_seed = abs(hash(file_path)) % 100000
```

这是错误的 deterministic seed 方案。

---

## 37.1 为什么错误

Python 默认对字符串 hash 有进程级随机 salt。

因此：

```text
process A:
hash("/music/a.mp3") = X

process B:
hash("/music/a.mp3") = Y
```

尤其 parallel exporter 使用多个 Python process。

所以各 worker 的 seed 可能不同。

---

# 38. 正确 seed 来源

优先使用：

```text
features.metadata.file_hash
```

如果这个 hash 本身是稳定内容/文件标识。

再转成 uint64：

```python
digest = hashlib.blake2b(
    file_hash.encode("utf-8"),
    digest_size=8
).digest()

track_seed = int.from_bytes(digest, "little")
```

不要：

```text
% 100000
```

没必要把 seed 压到 10 万种。

---

# 39. 当前更大的问题：track_seed 根本没有进入粒子系统

虽然：

```text
DynamicsBundle.track_seed
```

存在，

但：

```text
Scene
ParticleSystem
Renderer
```

仍大量调用：

```python
random.random()
random.uniform()
```

---

# 40. `app/dynamics/deterministic.py` 目前仍是 unused utility

它写得没问题。

但产品运行不使用，等于没有实现 determinism。

Round 3 必须真正接。

---

# 41. Particle 必须有 stable ID

当前 `Particle` 没有：

```text
particle_id
```

本轮增加：

```python
id: int
```

ParticleSystem：

```python
self.next_particle_id
```

递增。

不要使用 list index。

---

# 42. 发射随机数建议键设计

例如：

```text
stream_id = "beat_burst_angle"
tick      = simulation_tick
event_idx = i
```

或：

```text
particle_initial_speed
particle_initial_size
particle_hue
```

不同 stream 分开。

---

# 43. Scene 的随机 emission 也必须 deterministic

当前：

```python
if random.random() < emit_chance:
```

应基于：

```text
track_seed
simulation_tick
stream_id
```

---

# 44. Ambient emission 概率还存在 FPS 依赖

现在：

```python
p = emit_chance
```

每一帧抽一次。

60 FPS 与 30 FPS 单位秒产生事件数不同。

---

## 正确 Poisson-style 事件概率

假设：

```text
rate_per_sec = λ
```

则：

\[
p(dt)=1-e^{-\lambda dt}
\]

这样才与 fps 近似无关。

---

# 45. Beat / Onset 快速事件也要注意“提前触发”

当前 FeatureCache：

```python
get_events_near(time, window=0.08)
```

是：

```text
±80 ms
```

因此 beat 的 binary state 可能在真正 beat 前 80ms 就变 1。

Scene 又通过：

```python
beat > 0.6
```

检测 rising edge。

这可能让 beat burst 提前。

---

# 46. 推荐事件触发语义

用：

```text
last_audio_time < event_time <= current_audio_time
```

检测真正“跨过事件时间”。

比：

```text
abs(event-time)<80ms
```

更准确。

---

# 47. VisualContext 的 beat impulse 可使用 causal decay

例如：

\[
I_b(t)
=
s_b
e^{-(t-t_b)/\tau}
\]

仅当：

\[
t \ge t_b
\]

---

# 48. Onset event 也同理

即时 flash / spark 可以准确从事件时间触发。

慢 MaterialState 使用：

```text
onset envelope
transient density
```

即可。

---

# 49. 当前 Plasma“stochastic”其实不是 stochastic

当前：

```python
sin(r_norm*8 + theta*3)
cos(r_norm*8 - theta*3)
```

这是：

> deterministic static spatial oscillatory field

不是随机散射。

它没有：

```text
time
tick
particle_id
track_seed
```

---

# 50. 建议重新命名或真正实现

两个选择。

---

## 50.1 简单方案

把当前项叫：

```text
plasma_wave_scattering
```

不要叫 stochastic。

---

## 50.2 推荐方案

真正加入 deterministic time-correlated noise：

```text
track_seed
particle_id
coarse_tick
```

生成目标方向，

然后在多个 tick 间平滑。

---

# 51. Plasma noise 不要每帧白噪声

否则画面会抖成雪花。

建议相关时间：

```text
80~250 ms
```

---

# 52. `AnalyticalPESField.sample_force()` 可以接受 sampling context

推荐：

```python
sample_force(
    x,
    y,
    ...,
    material,
    particle_id,
    simulation_tick,
    track_seed,
)
```

如果不想让 dynamics.field 依赖粒子概念，可把 stochastic term 放 ParticleSystem。

这可能更干净：

```text
AnalyticalPESField
    只负责 deterministic spatial potential + curl

ParticleSystem
    负责 deterministic plasma stochastic kick
```

我更推荐后者。

---

# 53. 第六个问题：MaterialStateSequence 仍然没有 interpolation

当前：

```python
idx = int(time / dt)
return states[idx]
```

这是 zero-order hold。

---

# 54. 为什么建议插值

如果：

```text
trajectory = 60 Hz
export = 120 FPS
```

连续两帧会读取同一 state。

24/30 FPS 虽然落在不同 ticks，也有小 step。

---

# 55. 实现 state interpolation

对：

```text
order
excitation
mobility
defect
activity
phase weights
```

线性插值。

然后：

```text
weights 重新归一化
```

`phase_name`：

```text
argmax weights
```

---

# 56. MaterialStateSequence API 建议

```python
state_at(t, interpolate=True)
```

默认 interpolate。

内部 O(1)。

---

# 57. 第七个问题：Particle integration 仍然是 render-FPS driven

当前：

```python
sf = dt * 60
p.v += force * sf
p.x += velocity * sf
```

这是“60 FPS tuned”而不是严格时间积分。

---

# 58. Drag 甚至可能在超大 dt 下变负

当前：

```python
factor = 1 - (1-drag)*sf
```

如果：

```text
sf 足够大
```

factor 可以 < 0，速度反向。

---

# 59. Drag 应改为指数形式

如果 `drag60` 表示 60 FPS 每 tick 保留比例：

\[
v(t+dt)
=
v(t)
\,
drag60^{60dt}
\]

代码：

```python
drag_factor = drag60 ** (dt * 60.0)
```

不会变负。

---

# 60. Force integration 应直接使用秒

更明确地定义：

```python
ACCEL_SCALE
```

然后：

```python
vx += fx * accel_scale * dt
x += vx * dt
```

如果旧速度单位是“pixels per 60Hz frame”，最好一次性迁成：

```text
pixels / second
```

---

# 61. 推荐固定粒子 simulation tick

最稳：

```text
SIM_HZ = 60
SIM_DT = 1/60
```

Scene 维护 accumulator。

Renderer FPS 任意。

---

# 62. 如果本轮不想大改单位

至少先：

- drag 用指数；
- emission rate dt-aware；
- stochastic deterministic；
- 加 30/60fps regression test。

---

# 63. 第八个问题：Seek 实现名不副实

当前：

```python
scene.seek_to()
```

docstring：

```text
with deterministic particle warmup
```

实际只：

```text
clear effects
clear particles
query material/context
update field
```

没有 warmup。

---

# 64. MainWindow seek 因此会出现“空世界瞬间”

用户 seek 到 120s：

```text
MaterialState 已正确
Particles = []
```

随后几帧重新慢慢出生。

这与从头顺序播放到 120s 的视觉不同。

---

# 65. Seek 还没有 reset RingLayer / EnergyCore

当前：

```text
RingLayer
EnergyCore
audio_drive
```

可能保留 seek 前状态。

例如：

```text
180s -> 40s
```

粒子没了，

但 shell/core envelope 可能仍带 180s 的短期历史。

---

# 66. `scene.seek_to()` 真正应该做

```text
1. query material at target
2. clear particles
3. reset effects
4. reset RingLayer transient state
5. reset EnergyCore short state
6. reset audio_drive envelopes
7. reset event cursors
8. warmup short visual state
9. finish at exact target
```

---

# 67. Seek warmup 不需要恢复 MaterialState

Material 已预编译。

只恢复：

```text
particles
ring/core envelopes
effects
```

---

# 68. 建议 warmup 时间

根据实际最长短期视觉寿命。

当前 dust/star lifetime 以 60Hz frame 单位存在，迁秒后统计。

先取：

```text
VISUAL_WARMUP_SECONDS ≈ 5~8
```

但应该由真实最大 visible decay 决定。

---

# 69. Seek warmup 必须 deterministic

否则：

```text
顺序播放到 120s
```

和：

```text
seek 到 120s
```

仍然不同。

---

# 70. Exporter warmup 现在比 MainWindow 更接近正确

并行 worker 会：

```python
scene.seek_to(warmup_start)
```

然后从 warmup_start 循环到 segment start。

但是由于 RNG 仍是全局 random：

仍不能保证与串行完全一致。

---

# 71. Parallel seed 现在尤其错误

每个 worker：

```python
abs(hash(track_path)) % 100000
```

跨进程不稳定。

这一条必须优先修。

---

# 72. DynamicsBundle 创建代码现在复制了三遍

存在于：

```text
MainWindow
Sequential Export
Parallel Worker
```

每份都手写：

```text
calibration
context
trajectory
seed
```

这很危险。

---

# 73. 推荐集中成一个 factory

例如：

```python
def build_dynamics_bundle(
    feature_cache: FeatureCache,
) -> DynamicsBundle:
```

放：

```text
app/dynamics/context.py
```

或者 `trajectory.py`。

---

## 这样可以保证

所有路径：

```text
MainWindow
Sequential
Parallel
Tests
```

使用同样：

- calibration；
- contrast；
- seed；
- simulation_hz；
- trajectory options。

---

# 74. 不要继续在三个地方写 absolute import

统一 package import。

---

# 75. V2 compile failure 不应 silent legacy fallback

当前：

```python
except:
    print("[Dynamics V2 Compile Error]")
```

然后仍可走 legacy。

开发阶段这会隐藏严重 bug。

---

# 76. 推荐模式

默认开发：

```text
STRICT_V2 = True
```

V2 compile 失败：

```text
明确显示错误 / 测试失败
```

release 可允许 fallback，但 UI/日志必须明确：

```text
V2 unavailable — legacy visualization active
```

---

# 77. TrackCalibration 的 NaN 处理还有一个边缘漏洞

当前：

```python
np.percentile(
    flux_arr[~np.isnan(flux_arr)],
    95
)
```

判断只看：

```python
len(flux_arr) > 0
```

如果数组非空但全是 NaN：

```text
有效数组长度 = 0
```

percentile 会失败。

---

## 修复

分别：

```python
valid_flux = ...
valid_onset = ...
```

然后：

```python
if len(valid_flux) > 0
```

---

# 78. Silence / constant signal calibration 语义

当前如果：

```text
P95-P10 < 1e-3
```

`normalize_rms_db()` 返回：

```text
0.5
```

这对 constant nonzero signal 可以接受。

但对：

```text
all-zero silence
```

返回 0.5 会很奇怪。

---

# 79. 建议特殊处理 all-silence

如果：

```text
rms_reference <= silence_epsilon
```

则：

```text
normalize_rms_db(any near-zero) = 0
```

避免 silent track activity 被抬到 0.8。

---

# 80. 这条需要单测

输入：

```python
rms_arr = np.zeros(...)
```

输出：

```text
activity ≈ 0
```

---

# 81. MaterialState 需要验证 phase occupancy 是否 collapse

目前没有真实曲库统计。

算法：

```text
order
excitation
defect
→ prototype softmax
```

本身合理，

但权重可能使大部分音乐长期 Fluid。

---

# 82. 加 phase occupancy 开发脚本

```text
scripts/plot_v2_trajectory.py
```

对一首歌输出：

```text
mean w_c
mean w_f
mean w_p
```

以及：

```text
P10/P50/P90
```

---

# 83. 加跨曲目比较

至少本地：

```text
piano
pop
rock
EDM
ambient
noise-heavy
acoustic
```

如果都：

```text
Fluid 85%
```

需要调 prototype，而不是新增 Phase。

---

# 84. MaterialState 中 `excitation` 注释与范围也应一致

注释：

```text
E ∈ [0,2]
```

实际 target 基本 `[0,1]`，更新也不会超过 1 左右。

要么：

```text
注释改为 [0,1]
```

要么真正设计 >1 的语义。

建议统一 `[0,1]`，简单。

---

# 85. MaterialState 的 L3/L4 使用建议

第一版可以：

```python
exc_target = (
    0.25 * ctx.energy_fast
    + 0.12 * ctx.energy_slow
    + 0.20 * ctx.flux
    + 0.18 * ctx.onset
    + 0.20 * ctx.transient_density
    + 0.05 * max(ctx.energy_trend, 0.0)
)
```

---

# 86. Defect susceptibility

```python
susceptibility = (
    1.0
    + 0.20 * ctx.novelty
    + 0.12 * ctx.boundary_impulse
)
```

```python
damage *= susceptibility
```

不要过强。

---

# 87. Mobility

```python
mob_target = (
    0.35 * excitation
    + 0.35 * beat_density
    + 0.20 * defect
    + 0.10 * energy_slow
)
```

---

# 88. Order

继续主要由：

```text
tonality
harmonicity
spectral noise
defect
```

决定。

不要让 RMS 直接变成 order。

---

# 89. Renderer 中 fast event 与 slow material 仍要双通道

不要为了 V2 把 beat responsiveness 弄没。

---

## Slow

```text
MaterialState
GeometryControl
```

控制：

```text
世界是什么状态
```

---

## Fast

```text
beat/onset
```

控制：

```text
这个状态下发生什么瞬时事件
```

---

# 90. Fast event 应被 material 调制

同一 beat：

### Crystal

```text
短 nodal ripple
局部 crack
```

### Fluid

```text
circulation impulse
```

### Plasma

```text
fragment spray
```

这会显著减少“所有 beat 都是同一个 radial burst”的同质化。

---

# 91. Beat burst 当前仍固定是 massive radial particle burst

这仍是旧 Stormy-Pulse 最明显模板之一。

本轮可以先做轻量调制：

```text
burst radiality
burst angular spread
particle drag
fragment count
```

由 MaterialState 控制。

无需新增特效。

---

# 92. Renderer 第一阶段具体改哪些函数

至少检查并接入：

```text
_draw_harmonic_shell_layer
_draw_generative_structure
_draw_transient_lattice_layer
_draw_energy_core_layer
```

背景不必第一轮大改。

---

# 93. Harmonic Shell 推荐映射

```text
symmetry
    → lobe integer regularity

angular_lock
    → phase stability

coherence
    → multiple shell alignment

roughness
    → high-frequency radial perturbation

fragmentation
    → missing/weak arcs
```

---

# 94. Generative Structure 推荐映射

`structure_type` 保留为 style basis。

MaterialState 负责：

```text
circulation
fragmentation
roughness
coherence
```

例如：

```text
reactor + high fluid
```

也应该明显被扭曲成 circulation-rich reactor，

而不是永远静态 reactor。

---

# 95. Transient Lattice

这是最适合 defect 的现有层。

让：

```text
defect_density
```

改变：

- lattice continuity；
- local offset；
- line break；
- misalignment。

---

# 96. Energy Core

可以让：

```text
excitation
```

影响呼吸/辐射强度，

但不要：

```text
plasma = 更大更亮
```

这么单一。

---

# 97. Fragmentation 不要每帧无记忆随机生成

用：

```text
material defect history
+
deterministic spatial mask
```

稳定一段时间。

---

# 98. Geometry deterministic mask

例如：

```python
segment_damage(i, coarse_tick)
=
deterministic_float(
    track_seed,
    "ring_damage",
    coarse_tick,
    i,
)
```

只在：

```text
coarse_tick ≈ 0.2~0.5s
```

变化一次，

再平滑。

---

# 99. Renderer 的 global random 也要继续收口

当前 grain 初始化虽然通过 temporary seed 比较稳定，

但 seed 来源是：

```text
title_artist
```

建议统一为：

```text
DynamicsBundle.track_seed
```

这样所有随机层共享同一 track identity。

---

# 100. 不要使用 Python global `random.seed()` 临时切换状态

虽然保存/恢复 state 能工作，

但以后多线程/并行/异步容易出现隐患。

直接 deterministic function 更干净。

---

# 101. 测试：当前新增测试的优点

保留：

- RMS calibration monotonic test；
- analytical vs finite difference；
- legacy PhaseEngine not called；
- seek material equality。

这些方向正确。

---

# 102. 但当前 tests 仍远不足以证明 Round 2 文档要求

尤其缺：

```text
L3 causal
L3 aligned timeline
L3 interpolation
spectral contrast
band share
renderer geometry sensitivity
deterministic particles
stable seed
FPS particle independence
serial/parallel raw frame equivalence
seek warmup equivalence
```

---

# 103. 新增 `test_l3_causal_windows.py`

synthetic：

```text
0~10s RMS=0.1
10~20s RMS=1.0
```

在：

```text
t=9s
```

8s window 绝不能看到 10s 后高能量。

---

# 104. 新增 L3 timeline test

断言：

```python
len(times)
==
len(stats2[k])
==
len(stats4[k])
==
len(stats8[k])
```

---

# 105. 新增 interpolation test

在：

```text
t=4.5s
```

结果应介于 4s 与 5s。

---

# 106. 新增 transient density test

造 onset events：

```text
1, 1.5, 2, 2.5
```

检查：

```text
4s density
```

符合事件数/秒。

---

# 107. 新增 beat density test

无 beat：

```text
density=0
```

稳定 120 BPM：

```text
约 2 beats/s
```

归一化后符合定义。

---

# 108. 新增 contrast test

至少：

```text
raw spectral contrast
→ normalized [0,1]
```

并确认：

```text
line_thickness 不再永久 = 6
```

---

# 109. 新增 raw band share test

synthetic spectral power：

```text
bass = 8
mid = 1
high = 1
```

应：

```text
bass share ≈ 0.8
```

不能因为各 band 自归一化后变成约 1/3。

---

# 110. 新增 stable seed test

开两个独立 Python process。

给相同：

```text
metadata.file_hash
```

得到完全同一个：

```text
track_seed
```

这条专门防止重新用 Python `hash()`。

---

# 111. 新增 particle deterministic test

相同：

```text
track_seed
event
tick
```

生成的第一批粒子：

```text
angle
speed
size
life
hue
```

完全一致。

---

# 112. 新增 renderer geometry sensitivity test

无需 image snapshot。

将同一个 Theme/VisualDNA 分别输入：

```text
crystal geometry
fluid geometry
plasma geometry
```

让纯 geometry descriptor 或中间参数不同。

---

# 113. 如果现有 geometry 全写在 paint 里

建议提炼：

```python
compute_shell_geometry(...)
```

为纯函数。

不是为了架构洁癖，

而是为了能测试。

---

# 114. 新增 Seek visual warmup test

A：

```text
从 0 顺序模拟到 10s
```

B：

```text
scene.seek_to(10s)
```

比较：

```text
material
ring/core envelope
particle count/statistics
```

第一版不要求每粒子 bit-identical，

但接 deterministic 后应逐步收紧。

---

# 115. 新增 sequential / parallel state test

至少在 segment boundary：

```text
MaterialState
Context
GeometryControl
```

必须一致。

---

# 116. 最终再加 raw image seam test

不要先做 MP4 bitwise compare。

比较：

```text
QImage / RGBA frame
```

---

# 117. Round 3 推荐实施顺序

请严格按下面顺序。

---

## R3-0：修 Analysis Semantics

修改：

```text
window.py
features.py
spectrum.py
extractor.py
section.py（如需要）
cache version
```

完成：

- causal L3；
- aligned windows；
- interpolation；
- contrast；
- band shares；
- stable section timing。

---

## R3-1：修 VisualContext

完成：

```text
real transient_density
real beat_density
real energy trend
real spectral tilt
causal boundary impulse
```

删除所有 placeholder。

---

## R3-2：让 MaterialState 真正使用 L3/L4

仅调整已有 MaterialStateEngine。

禁止创建新 engine。

---

## R3-3：集中 DynamicsBundle factory

MainWindow / Sequential / Parallel 全部改用同一个 builder。

同时修：

```text
stable seed
contrast calibration
simulation_hz
```

---

## R3-4：GeometryControl → Scene/RingLayer/Renderer

这是本轮最重要视觉阶段。

完成至少：

```text
harmonic shell
generative structure
transient lattice
```

的 continuous morph。

---

## R3-5：Deterministic Particle / Event RNG

完成：

```text
stable particle id
dt-aware emission
keyed random
```

---

## R3-6：Particle time integration

优先：

```text
drag exponential
event probability dt-aware
```

再决定是否 fixed-step accumulator。

---

## R3-7：真正 Seek rebuild

包括：

```text
ring/core/envelope reset
deterministic warmup
```

---

## R3-8：Parallel seam verification

此时再测 serial / parallel。

---

## R3-9：Legacy cleanup

旧：

```text
visual.phase_engine
visual.pes_field
```

移到：

```text
legacy
```

或明确标 deprecated。

不要让新 Agent 再误用。

---

# 118. 推荐 commit 粒度

```text
commit 1
fix(analysis): make L3 windows causal, aligned and interpolated

commit 2
fix(analysis): normalize spectral contrast and preserve raw band shares

commit 3
fix(dynamics): consume real L3/L4 signals in VisualContext and MaterialState

commit 4
refactor(dynamics): centralize DynamicsBundle creation and stable track seed

commit 5
feat(visual): route GeometryControl into RingLayer and Renderer

commit 6
feat(visual): morph harmonic shell and generative structure from material state

commit 7
feat(random): replace scene and particle global RNG with keyed deterministic streams

commit 8
fix(simulation): make particle drag/emission timestep-aware

commit 9
fix(seek): deterministically rebuild transient scene state after arbitrary seek

commit 10
test(v2): verify causal context, geometry sensitivity, determinism and export seams

commit 11
chore(v2): deprecate legacy phase/PES runtime
```

---

# 119. 本轮禁止“一个大提交里又塞计划文档四千行”

计划文档可以保留，

但 commit stats 需要能看出真实代码量。

最好计划文档单独 commit，

代码按上述功能拆。

---

# 120. 真实验收指标：代码层

Round 3 完成后 grep：

```text
renderer.py
```

应该能找到：

```text
current_material_state
geometry_control
fragmentation
circulation
coherence
```

至少相应语义。

---

# 121. 真实验收指标：旧 phase

默认 V2 播放：

```text
old PhaseEngine.update
```

仍不能被调用。

---

# 122. 真实验收指标：RingLayer

V2 active：

```text
RingLayer
```

必须收到：

```text
GeometryControl
```

或等价连续 material parameters。

不能继续：

```text
phase_state=None
```

---

# 123. 真实验收指标：随机性

全项目 grep：

```text
random.random
random.uniform
```

所有 simulation-relevant 调用必须被分类。

不是所有随机都必须删除，

但必须明确：

```text
render-only
or deterministic simulation
```

---

# 124. 真实验收指标：hash

全项目不得再用：

```python
hash(path)
```

作为跨进程持久 seed。

---

# 125. 真实验收指标：L3

`window.py` 不得再以：

```text
start=t
end=t+window
```

作为默认 window semantics。

---

# 126. 真实验收指标：contrast

不得再出现：

```python
raw_librosa_contrast > 0.45
```

这种 `[0,1]` 假设。

---

# 127. 真实验收指标：band ratio

GlobalFeatureSet 的：

```text
bass_ratio
mid_ratio
high_ratio
```

必须来自同尺度 raw power share。

---

# 128. 真实验收指标：Seek

从：

```text
180 -> 40
```

后：

- material 正确；
- ring/core 不继承 180s；
- particles 不为空很久；
- 重建可复现。

---

# 129. 真实验收指标：视觉

同一 VisualDNA 下人工注入：

### Crystal

```text
order=.9
defect=.05
w_c=.9
```

### Fluid

```text
mobility=.9
w_f=.85
```

### Plasma

```text
excitation=.95
defect=.85
w_p=.9
```

主体结构必须一眼不同，

且中间状态连续。

---

# 130. 如果只看到粒子路线不同，不算通过

V2 目标不是：

> “同一个环 + 不同粒子运动。”

而是：

> “整块人工物质的结构状态不同。”

---

# 131. Round 3 暂时仍不做真正 Chladni

等现有 shell 能随：

```text
symmetry/angular_lock/coherence
```

稳定 morph 后，

下一轮再加入真实 nodal basis。

---

# 132. Round 3 暂时仍不做 GPU 大迁移

先让 CPU/QPainter 的语义正确。

GPU 只需要继续能显示同一 Scene。

---

# 133. Round 3 暂时不增加 phase 数量

如果效果不好，

先调：

```text
calibration
prototype center
beta
time constants
geometry gains
```

不要马上：

```text
第四相
第五相
```

---

# 134. 性能注意：MaterialTrajectory compile 现在每 tick 调 `VisualContext.at`

60Hz × 5min：

```text
18,000 次
```

本身没问题。

但是 VisualContext 每次：

```text
get_events_near()
```

当前使用全数组 `np.where`。

长曲可能放大成本。

---

# 135. 推荐 EventFeatureSet 查询优化

改为：

```text
np.searchsorted
```

获取 nearest/previous event。

这也方便实现 causal beat impulse。

---

# 136. MainWindow compile 是否阻塞 UI

当前 bundle compile 在 analysis finished 回调中执行。

需要实际 benchmark。

---

## 如果：

```text
< 200~300 ms
```

可以接受。

---

## 如果：

```text
> 1 s
```

考虑在 AnalysisWorker 内完成 dynamics compile，

不要卡 UI。

不要先假设。

---

# 137. Export worker 每个进程重编 MaterialTrajectory 是否可接受

通常几十 KB/几 MB state，非常便宜。

如果 compile < 数百 ms，可以接受。

不必为了少量 CPU 引入复杂 IPC。

---

# 138. MaterialStateSequence memory 也无需过度优化

5min × 60Hz ≈ 18k states。

十几个 float 级别，

完全不是问题。

---

# 139. 实际视觉调参时不要只盯 phase_name

主要看：

```text
order
excitation
mobility
defect
GeometryControl
```

---

# 140. 增加 trajectory debug output

建议脚本：

```text
scripts/plot_v2_trajectory.py
```

输出：

```text
time-order
time-excitation
time-defect
time-mobility
phase weights
section boundaries
```

以及：

```text
order vs excitation phase-space plot
```

---

# 141. 为什么这一步重要

如果相空间本身：

```text
所有歌几乎一样
```

Renderer 再漂亮也会同质化。

如果相空间不同，

但画面一样，

问题就在 Geometry mapping。

这样可以定位。

---

# 142. 建议加 GeometryControl 时间曲线

同一脚本同时画：

```text
symmetry
circulation
fragmentation
roughness
```

看是否有足够动态范围。

---

# 143. 防止过度 smoothing

当前已有：

```text
Track calibration
L3 slow context
Material relaxation
phase weight smoothing
Scene audio_drive smoothing
Ring smoothing
```

如果 Renderer 再加一层很慢 smoothing，

最终会严重迟钝。

---

# 144. 建议原则

### 宏观状态

MaterialState 已经负责 smooth。

### Geometry

尽量直接跟 MaterialState。

### Fast event

单独 envelope。

---

# 145. 反同质化的真正测试

不要只看：

```text
不同歌颜色不同
```

---

## 对同一歌

观察：

```text
intro
verse
pre-climax
climax
post-climax
```

主体 topology 是否真的变化。

---

## 对不同歌

观察：

```text
轨迹
phase occupancy
defect history
geometry control
```

是否明显不同。

---

# 146. 特别测试 Ambient

应：

- beat density≈0；
- 没 fake 120 BPM；
- mobility 不被 beat 推高；
- 可由 tonal field / slow energy 演化；
- 不应该静态死画面。

---

# 147. 特别测试 Metal / Noise-heavy

tonal confidence 低时：

```text
potential 弱
```

但：

```text
curl / plasma scattering 强
```

不能“整个 field 关闭”。

---

# 148. 特别测试 Classical

动态范围大，

高潮可明显：

```text
excitation ↑
defect ↑
```

但安静段落能重建 order。

不要因为整体 RMS 低就永远 crystal。

---

# 149. 特别测试 Brickwall Pop

因为 track-relative calibration，

不能全程 plasma。

必须仍有段内相对动态。

---

# 150. Round 3 最终测试清单

至少增加/完成：

```text
[ ] test_l3_causal_no_future_leak
[ ] test_l3_equal_lengths
[ ] test_l3_tail_valid
[ ] test_l3_interpolation
[ ] test_real_transient_density
[ ] test_real_beat_density
[ ] test_spectral_contrast_normalization
[ ] test_raw_band_power_share
[ ] test_silent_track_activity_zero
[ ] test_stable_seed_cross_process
[ ] test_material_consumes_l3
[ ] test_material_boundary_susceptibility
[ ] test_material_sequence_interpolation
[ ] test_geometry_control_changes_renderer_params
[ ] test_v2_ring_receives_geometry
[ ] test_particle_emission_deterministic
[ ] test_particle_drag_no_negative_factor
[ ] test_seek_resets_ring_core
[ ] test_seek_deterministic_warmup
[ ] test_serial_parallel_material_equal
[ ] test_serial_parallel_geometry_equal
```

---

# 151. 本轮人工验收清单

```text
[ ] 同一首歌主体形态会连续变化
[ ] Crystal/Fluid/Plasma 不只是粒子运动不同
[ ] 高潮后存在结构记忆
[ ] 静音不会强流动
[ ] Ambient 不假拍
[ ] noisy/plasma 不因 tonal confidence 低而静止
[ ] seek 后不出现明显空场/旧状态残留
[ ] 重复 seek 到同一点结果相近
[ ] 串行/并行 segment 边界无明显跳变
[ ] 30/60fps 宏观物态一致
```

---

# 152. 对当前 `cfaff45` 的完成度评价

大致可以这样理解：

| 子系统 | 当前状态 |
|---|---|
| Material math | 较好 |
| MaterialTrajectory | 已真正接入 |
| MainWindow integration | 已接 |
| Sequential exporter | 已接 |
| Parallel exporter | 已接宏观状态 |
| Analytical PES | 已接 |
| Particle material force | 初步接入 |
| L3 real semantics | 未完成 |
| L4 → Material dynamics | 基本未完成 |
| Spectral contrast | 未修 |
| Raw band share | 未修 |
| GeometryControl → Renderer | 未接 |
| RingLayer V2 | 未接 |
| Deterministic RNG | 未接 |
| Stable cross-process seed | 错误 |
| Seek macro state | 已接 |
| Seek transient rebuild | 未完成 |
| Particle FPS independence | 未完成 |

所以：

> **cfaff45 是一个真正的“V2 runtime bridge”提交，但还不是 V2 visual closure。**

---

# 153. 本轮最重要的一句话

接下来不要再证明：

> “MaterialState 能算出来。”

这件事已经证明了。

现在要证明：

> **MaterialState 能真正改变整个 Stormy-Pulse 世界的形态，而且这个变化在播放、Seek、串行导出和并行导出中都具有一致的时间语义。**

---

# 154. 给开发 Agent 的最终执行摘要

请从 `cfaff45` 当前状态继续，不要重新设计已有 V2。

优先顺序：

```text
1. 修 L3 causal / aligned / interpolation
2. 修 spectral contrast / raw band share
3. VisualContext 去掉 density/trend placeholder
4. MaterialState 真正使用 L3/L4
5. 集中 DynamicsBundle factory + stable BLAKE2 seed
6. MaterialStateSequence interpolation
7. GeometryControl 真正接 RingLayer / Renderer
8. 主体 shell / structure / lattice 连续 morph
9. deterministic particle/event RNG
10. dt-aware particle simulation
11. seek reset + deterministic warmup
12. serial/parallel seam tests
13. legacy cleanup
```

本轮禁止新增：

```text
Chladni
Navier-Stokes
Skyrmion
3D
GPU particle renderer
new phase
new ML classifier
```

直到：

```text
GeometryControl
```

已经能在现有 CPU Renderer 中显著改变主体结构。

---

# 155. 最终验收句

Round 3 真正完成时，下面这句话应该与代码完全一致：

> **Stormy-Pulse now derives a causal, multiscale VisualContext from the full audio analysis, precompiles a history-dependent MaterialTrajectory, and uses that same absolute-time material state to drive both particle forces and continuous geometry morphing. Random visual events are keyed deterministically, seeking reconstructs transient visual state, and serial/parallel rendering share the same material and geometry timeline.**

如果其中任何一段仍只是注释、未使用字段、unused utility 或 legacy fallback，

就不应宣告 Round 3 完成。
