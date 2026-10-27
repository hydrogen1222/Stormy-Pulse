# Stormy-Pulse V2 Round 6：最终语义收口、完整可复现性与真实视觉验收计划

> **文档性质**：Round 5 完成后的源码审计与下一轮执行计划  
> **审计基线**：GitHub `main` 最新提交 `fb12c666388eebbadd28116f9e2434814651cb8d`  
> **提交标题**：`feat(v2): complete round 5 geometry determinism and semantic closure`  
> **审计日期**：2026-08-26  
>
> **本轮建议性质**：这是一次“收尾轮”，不是再开新架构。  
> Round 5 已经把 V2 从“部分接线”推进到“主体结构真正开始响应 MaterialState”的阶段。  
> Round 6 的目标是把剩余几个语义与可复现性漏洞补完，然后停止基础架构重构，转入真实歌曲视觉验收与艺术调优。

---

# 0. Round 5 总体评价

这次提交是真正有分量的一轮。

当前最新 HEAD 已经做到了：

```text
✅ Generative Structure 四种 basis 都开始读取 GeometryControl
✅ Transient Lattice 已读取 circulation / coherence / fragmentation / defect
✅ RingLayer defect damage 已改成连续 healing，而不是单纯开关
✅ raw band shares 已从原始频谱功率计算
✅ FrameFeatureSequence 已保存 band_shares
✅ VisualContext.spectral_tilt 已优先使用 band_shares
✅ cache 已 bump 到 v6
✅ EventFeatureSet 已有 get_events_crossed()
✅ Scene beat trigger 已开始使用 crossed-event
✅ ParticleSystem emit / emit_burst 已开始使用 keyed deterministic randomness
✅ stable particle_id 已真正进入粒子初始化
✅ Renderer grain 已开始使用 deterministic helper
✅ Parallel exporter 已改成让 Scene.rebuild_to_time() 负责 preroll
✅ Scene rebuild owner 已比上一轮清晰
```

这说明此前最重要的：

```text
MaterialState
    ↓
GeometryControl
    ↓
Generative Structure / Ring / Lattice
```

终于真实成立。

因此 Round 6 不要继续新增新 Phase、新 PES、新 Renderer 架构。

---

# 1. 但当前提交仍不能严格称为“semantic closure complete”

主要剩下四类问题：

```text
A. raw band shares 已计算，但 global bass/mid/high ratio 仍然用旧 band drive
B. beat crossed-event 已接 Scene，但 onset crossed-event 没真正接入
C. deterministic helper 已接一部分，但 Scene / Effects / Renderer 仍有 global random
D. Round 5 tests 主要验证组件能力，没有充分验证真实主链的 end-to-end 行为
```

这四项是 Round 6 的核心。

---

# 2. P0：band_shares 已有，但 GlobalFeatureSet 仍然吃旧 band drive

这是 Round 5 最大的“语义只完成一半”问题。

---

## 2.1 当前已经做对的部分

`spectrum.py` 已经：

```python
raw_energies[name] = np.sum(S_power[bins], axis=0)

raw_stack = ...
tot_power = ...
raw_shares = raw_stack / tot_power
```

即：

\[
share_i(t)
=
\frac{P_i(t)}
{\sum_j P_j(t)}
\]

这是我们一直要求的真正 cross-band power share。

---

## 2.2 FrameFeatureSequence 也已经保存

当前：

```python
band_shares: Optional[np.ndarray]
```

并在：

```python
get_frame_dict_at_time()
```

中返回插值后的：

```text
band_shares
```

VisualContext 也已经用它计算 spectral tilt。

这些都正确。

---

# 3. 但是 GlobalFeatureSet 仍然没有用 raw band shares

当前 `_compute_globals_and_semantics()` 仍然：

```python
b_mean = np.mean(bass)
m_mean = np.mean(mid)
h_mean = np.mean(high)

tot = b_mean + m_mean + h_mean
b_ratio = b_mean / tot
m_ratio = m_mean / tot
h_ratio = h_mean / tot
```

这里的：

```text
bass
mid
high
```

仍然是：

> 每个 band 已经分别独立归一化过的 animation drive。

---

# 4. 所以当前两个世界语义不一致

### VisualContext

已经：

```text
spectral_tilt <- raw band_shares
```

### GlobalFeatureSet

仍：

```text
bass_ratio/mid_ratio/high_ratio <- band_drive
```

---

# 5. 这会继续污染什么？

至少：

```text
structure_type
pressure
sparkle
warmth
lift
detail_style
```

尤其：

```python
if b_ratio > 0.5:
    structure_type = "reactor"

elif h_ratio > 0.4:
    structure_type = "vortex"
```

仍然使用“假比例”。

---

# 6. Round 6 第一优先级：GlobalFeatureSet 改用 raw shares

推荐 `_compute_globals_and_semantics()` 增加：

```python
band_shares: np.ndarray
```

shape：

```text
(N_frames, 6)
```

---

## 6.1 全局 share

定义：

```python
global_shares = np.mean(band_shares[active_frames], axis=0)
```

最好对低能量/静音 frame 做 activity weighting。

---

## 6.2 推荐 activity weighted mean

例如：

\[
w_t =
\frac{\mathrm{RMS}_t}
{\sum_t \mathrm{RMS}_t+\epsilon}
\]

然后：

\[
\bar{s}_i
=
\sum_t w_t s_i(t)
\]

这样长静音不会把 share 统计拖偏。

---

# 7. Global bass/mid/high 需要明确 6 band aggregation

当前 6 band：

```text
bass
low_mid
mid
high_mid
high
presence
```

可以定义：

```text
global_bass_share
=
bass

global_mid_share
=
low_mid + mid + high_mid

global_high_share
=
high + presence
```

然后保证：

\[
bass + mid + high \approx 1
\]

---

# 8. 这时才可以继续叫：

```text
bass_ratio
mid_ratio
high_ratio
```

否则应该叫：

```text
bass_drive_ratio
```

---

# 9. Structure prior 再继续使用它们才有意义

这时：

```python
if bass_ratio > ...
```

才真的表示：

> 这首歌的整体频谱功率偏低频。

---

# 10. Round 6 必须加 end-to-end global spectral semantics test

不要只测：

```text
compute_band_energies_6 returns shares
```

还要测试：

```text
shares
    ↓
extractor
    ↓
GlobalFeatureSet
```

---

## synthetic bass-heavy

构造：

```text
bass raw power ≫ others
```

应：

```text
GlobalFeatureSet.bass_ratio
```

显著最大。

---

## synthetic high-heavy

应：

```text
high_ratio
```

显著最大。

---

# 11. 当前 Round 5 test 没覆盖这个问题

现有测试只验证：

```text
raw shares sum ≈ 1
bass raw share > 0.7
```

它没有验证：

```text
GlobalFeatureSet
```

真的使用这些 shares。

所以测试绿并不能证明 semantic migration 完成。

---

# 12. P0-2：crossed onset API 已写，但 Scene 没真正用

这是第二个典型的“能力存在 ≠ 产品路径使用”的问题。

---

# 13. 当前 crossed API 正确

`EventFeatureSet.get_events_crossed()`：

```text
prev_time < event_time <= curr_time
```

使用 `np.searchsorted`。

这是正确实现。

---

# 14. Scene 当前只真正消费 crossed["beat"]

当前：

```python
crossed = events_obj.get_events_crossed(prev_t, self.time)

if crossed["beat"] > 0.4:
    beat_event_triggered = True
```

---

# 15. 但 crossed["onset"] 被忽略了

后面仍然：

```python
if onset > 0.75
    and time-last_onset > 0.1
    and time-last_beat > 0.2:

    onset_event_triggered = True
```

这仍是：

> 当前连续 onset envelope threshold

而不是：

> 真正跨过 onset event。

---

# 16. 所以当前 fast-event causality 只完成一半

### Beat

✅ crossed-event causal

### Onset

❌ 仍然 envelope threshold

---

# 17. Round 6 应统一

```python
if events_obj is not None:
    crossed = events_obj.get_events_crossed(prev_t, self.time)

    beat_event_strength = crossed["beat"]
    onset_event_strength = crossed["onset"]
```

---

# 18. Fast onset spark 用：

```text
crossed onset
```

---

# 19. Slow Material dynamics 继续用：

```text
L1 onset envelope
L3 transient_density
```

两者职责分开。

---

# 20. 不要用 crossed onset 替代所有 onset envelope

否则 MaterialState 会太离散。

---

# 21. Beat 也可以类似

### Fast burst

```text
crossed beat
```

### Material mobility

```text
beat_impulse causal decay
beat_density
```

---

# 22. onset crossed event 需要避免和 beat 重叠双触发

当前已有：

```text
time-last_beat > 0.2
```

新方案可以：

如果同一窗口：

```text
beat crossed
onset crossed
```

同时发生，

可以让：

```text
beat burst
```

主导，

onset spark：

```text
减弱或跳过
```

---

# 23. P0-3：ParticleSystem 本身 deterministic，但 Scene 调用没把 track_seed 传进去

这是非常重要的细节。

---

## 当前 ParticleSystem.emit()

支持：

```python
track_seed=42
```

并真正使用：

```text
deterministic_float
deterministic_signed
```

---

## emit_burst()

也支持：

```python
track_seed=42
```

---

# 24. 但 Scene 当前调用 beat burst 时没有传 track_seed

当前：

```python
self.particles.emit_burst(
    ...,
    chaos,
    energy
)
```

于是：

```text
track_seed 使用默认 42
```

---

# 25. onset spark emit 也没传

同样默认：

```text
42
```

---

# 26. ambient emission 内 particle emit 也没传

所以虽然：

> 同一次逻辑路径会 reproducible，

但所有歌曲实际上会使用相同的 particle pseudo-random pattern family。

---

# 27. 这不是“不可复现”，但不是我们设计的“track-keyed determinism”

应该：

```python
track_seed = (
    self.dynamics_bundle.track_seed
    if self.dynamics_bundle is not None
    else 42
)
```

然后所有：

```text
emit
emit_burst
stochastic particle behavior
```

都传进去。

---

# 28. P0-4：Scene 本身仍有 global random

当前 onset spark origin：

```python
angle = random.random() * 2π
```

---

# 29. Ambient emission

仍然：

```python
if random.random() < emit_chance:

    angle = random.random() * 2π
```

---

# 30. 这意味着 Particle 参数虽然 deterministic

但是：

```text
粒子是否生成
粒子从哪里生成
```

仍不 deterministic。

---

# 31. 所以完整 particle simulation 仍不 deterministic

这是 Round 6 必修。

---

# 32. Scene 随机统一使用 deterministic helper

---

## 32.1 需要 simulation tick

可以：

```python
sim_tick = int(round(self.time * 60.0))
```

或：

```text
fixed tick if future fixed-step
```

---

## 32.2 ambient emission decision

使用：

```python
u = deterministic_float(
    track_seed,
    "ambient_emit",
    sim_tick,
)
```

---

# 33. 但仍需 dt-aware 概率

当前：

```python
emit_chance
```

直接作为每帧 probability。

应转成 rate。

---

# 34. 例如定义

```python
lambda_per_second = base_rate * emit_drive
```

然后：

\[
p(dt)=1-e^{-\lambda dt}
\]

---

# 35. 这样：

```text
30 FPS
60 FPS
120 FPS
```

每秒 ambient emission 数量才接近一致。

---

# 36. ambient spawn angle

用：

```python
deterministic_float(
    track_seed,
    "ambient_angle",
    sim_tick,
)
```

---

# 37. onset spark origin angle

不要用 global random。

可以：

```text
track_seed
event_id
spark_index
```

---

# 38. Event ID 建议

最好让：

```text
get_events_crossed()
```

未来返回 event index。

---

# 39. 如果暂时不改 API

也可以：

```text
quantized onset event time
```

作为 deterministic key。

---

# 40. P0-5：Effects camera shake 仍然 global random

当前：

```python
camera_shake_x = (random.random()-0.5)*...
camera_shake_y = ...
```

---

# 41. 所以即使 Scene/Particles 全 deterministic

同一 onset：

```text
camera offset
```

还是不同。

---

# 42. EffectState.trigger_transient() 应支持 deterministic seed/event key

例如：

```python
trigger_transient(
    strength,
    track_seed,
    event_tick,
)
```

---

# 43. 方向：

```python
deterministic_signed(...)
```

---

# 44. P0-6：Renderer 还剩 global random high-frequency spikes

Renderer 已经很好地把 grain 改成 deterministic。

但是 `_draw_atmosphere_layer`/对应 high spike 区域仍：

```python
angle = random.random()
outer_r = ... + random.random()
```

---

# 45. 这是典型 render-only nondeterminism

同一 Scene：

```text
同一 timestamp
```

调用：

```python
render_to_image()
```

两次，

spikes 会不同。

---

# 46. 应改为 absolute-time keyed random

```python
render_tick = int(round(scene.time * 60))
```

对 spike `i`：

```python
angle_u = deterministic_float(
    track_seed,
    "hf_spike_angle",
    render_tick,
    i,
)
```

---

# 47. outer radius 同理

这样：

```text
重复 draw 同一帧
```

完全一致。

---

# 48. Renderer __init__ 初始 `_grain_points` 仍使用 global random

虽然 `set_track_info()` 后会重新生成 deterministic grain，

但在：

```text
set_track_info 前
idle render
test render
异常 fallback
```

仍可能使用随机 grain。

---

# 49. 建议初始 grain 也 deterministic default seed

例如：

```text
seed=0
```

不用 global random。

这样可以彻底删除 Renderer 中 `import random`。

---

# 50. Round 6 可以把目标定成：

```bash
grep -R "random.random\|random.uniform" app/visual
```

simulation/render-relevant 结果应为：

```text
0
```

或只剩明确非视觉用途。

---

# 51. P1：Generative Geometry 这次已经真正闭环

这一项需要明确表扬，也不要重复重写。

---

## Reactor

已经读取：

```text
symmetry
circulation
fragmentation
roughness
defect_density
```

---

## Vortex

已经读取：

```text
circulation
coherence
roughness
symmetry
```

---

## Pulse

已经读取：

```text
angular_lock
circulation
fragmentation
roughness
```

---

## Organic

已经读取：

```text
symmetry
coherence
roughness
```

所以：

```text
structure_type
```

现在已经更像：

> style basis

而不是：

> 唯一 Material phase。

这部分属于 Round 5 真正完成项。

---

# 52. 但仍建议一个小补强：Organic 缺 circulation/fragmentation

Organic 当前主要：

```text
symmetry
coherence
roughness
```

可以考虑小幅引入：

```text
circulation
fragmentation
```

但不是 blocker。

---

# 53. Transient Lattice 也已经真接 GeometryControl

当前：

```text
circulation
coherence
fragmentation
defect_density
```

已经进入。

这一项通过。

---

# 54. Harmonic Shell 仍主要使用部分 GeometryControl

当前明显使用：

```text
symmetry
coherence
roughness
```

如果想进一步完善：

```text
angular_lock
circulation
fragmentation
```

还可以继续加入。

但这已经属于艺术优化，不是架构 blocker。

---

# 55. Ring defect 已有 continuous healing

这也是真进步。

当前：

```text
damage_current
```

会：

```text
damage 快
healing 慢
```

这已经比上一版 binary flicker 好。

---

# 56. 但 Ring damage 仍是 ring-level，不是 segment-level

当前：

```text
一个 ring
一个 damage_current
broken_segments[ring]
```

所以如果 broken：

> 整条 ring 的某些绘制行为统一弱化。

---

# 57. 以后做更高级视觉时可以升级成：

```text
ring × angular segment damage field
```

但 **Round 6 不必做**。

先看真实歌曲画面是否已经足够丰富。

---

# 58. P1：raw band share cache v6 已做对

cache 已经：

```text
v6
```

这意味着 schema migration 至少有版本隔离。

---

# 59. 但 README 仍写 v4 cache

仓库 README 当前：

```text
文件名形如 v4_<hash>.npz
```

已经过期。

---

# 60. Round 6 顺手更新文档

至少：

```text
README
PROJECT_TECHNICAL_DOC
```

不要让用户照着 v4 文档理解 v6。

---

# 61. P1：Scene rebuild warmup ownership 这次基本收口

Parallel worker 当前：

```python
scene.rebuild_to_time(
    start_time,
    warmup_seconds=preroll_sec
)
```

然后直接从：

```text
start_frame
```

开始输出。

没有上一版：

```text
scene internal warmup
+
export external frame warmup loop
```

了。

这一项通过。

---

# 62. 但是 `rebuild_to_time()` 的 warmup dt 固定 0.033

也就是约：

```text
30 Hz
```

不管：

```text
export fps
```

是多少。

---

# 63. 这不一定是错误

如果我们定义：

```text
visual transient simulation canonical warmup = 30 Hz
```

可以。

---

# 64. 但正常实时 Scene.update 仍按 render dt

因此：

```text
顺序播放
```

和：

```text
rebuild warmup
```

的粒子轨迹可能并不完全一致。

---

# 65. 这说明“deterministic warmup”仍不是严格 deterministic trajectory reconstruction

它更准确是：

> deterministic approximate warmup.

---

# 66. 如果未来要求严格 seek==sequential

最终还是要：

```text
fixed visual simulation tick
```

---

# 67. Round 6 是否必须做 fixed-step？

我的建议：

**先不要。**

先补完 global RNG 与 track seed。

然后实测：

```text
sequential vs seek
serial vs parallel
```

差异。

---

# 68. 如果肉眼/统计已经足够一致

固定步长可以延后。

---

# 69. 如果 segment seam 仍明显

再把：

```text
particle/effect simulation
```

统一成固定：

```text
60 Hz or 30 Hz
```

canonical tick。

---

# 70. Round 5 tests 的主要不足

这轮测试相比以前已经明显好很多：

```text
✅ cross-process helper test 是真的 subprocess
✅ particle deterministic emit 是真的行为测试
✅ event API causality test 是真的行为测试
✅ ring damage healing 是真的行为测试
```

这是值得肯定的。

---

# 71. 但仍有明显 coverage gap

---

## 71.1 没验证 Scene 传 track_seed

ParticleSystem 测试直接：

```python
ps.emit(... track_seed=999)
```

能证明：

> ParticleSystem API 能 deterministic。

不能证明：

> Scene 实际传了 track seed。

而当前源码确实没有传。

---

# 72. 新增：

```text
test_scene_particle_emission_uses_track_seed
```

最好 monkeypatch ParticleSystem.emit/emit_burst 捕获参数。

---

# 73. 71.2 没验证 Scene onset crossed-event

API test：

```text
get_events_crossed works
```

不等于：

```text
Scene uses crossed onset
```

---

# 74. 增：

```text
test_scene_onset_does_not_fire_before_event
```

---

# 75. 71.3 没验证 GlobalFeatureSet 用 raw band shares

这就是当前最大 semantic 漏洞。

增：

```text
test_global_spectral_ratios_use_raw_band_shares
```

---

# 76. 71.4 没验证 Renderer same-time output deterministic

增：

```text
test_renderer_repeat_same_timestamp_same_rgba
```

如果 Qt CI 可行。

---

# 77. 如果不方便完整 offscreen compare

至少测试 high-frequency spike geometry helper。

---

# 78. 71.5 `test_scene_rebuild_to_time()` 太弱

当前只：

```python
scene = Scene()
scene.rebuild_to_time(1.5)
assert scene.time == 1.5
```

因为 scene 没 DynamicsBundle，

它根本没有测试真正 warmup。

---

# 79. 所以这个测试几乎不能证明：

```text
centralized warmup works
```

---

# 80. 必须构造真正 DynamicsBundle / FeatureCache fixture

然后：

```text
rebuild_to_time
```

前后比较：

- particle count；
- material state；
- ring state；
- effect state；
- repeatability。

---

# 81. Round 6 推荐新测试列表

```text
test_global_spectral_ratios_use_raw_shares
test_global_structure_prior_responds_to_raw_shares
test_scene_beat_crossed_event_used
test_scene_onset_crossed_event_used
test_scene_particle_emit_receives_track_seed
test_scene_ambient_emission_deterministic
test_effect_camera_shake_deterministic
test_renderer_spikes_deterministic_same_time
test_renderer_initial_grain_has_no_global_random
test_rebuild_with_real_bundle_populates_transients
test_rebuild_same_time_repeatable
test_parallel_segment_first_frame_matches_reference_statistically
```

---

# 82. P1：current onset handling 还有一个重复语义问题

Scene 当前：

```text
crossed beat
```

但：

```text
onset threshold
```

而 `audio_drive["onset"]` 又由：

```text
onset and beat_strength
```

共同平滑。

所以：

```text
onset
beat
fast transient
```

仍然有一点概念混合。

---

# 83. 建议最终分三条

### `onset_envelope`

连续量。

### `beat_impulse`

因果衰减。

### `fast_event`

crossed discrete trigger。

---

# 84. Renderer 只用 continuous drive

Scene effect trigger 用 event。

MaterialState 用 multiscale context。

这样最干净。

---

# 85. P1：beat_confidence 目前仍是粗糙 proxy

Extractor：

```python
beat_confidence = 1.0 if len(beat_times) > 10 else 0.2
```

这个很粗。

---

# 86. 但它不属于 Round 6 blocker

可以以后再基于：

```text
beat regularity
peak strength consistency
tempo stability
```

做更合理 confidence。

目前先不扩大范围。

---

# 87. P1：Global structure prior 阈值可能需要重新校准

等改成 raw shares 后：

```text
b_ratio > 0.5
h_ratio > 0.4
```

这些旧阈值可能不再合适。

---

# 88. 不要机械保留旧阈值

因为旧值是为“drive ratios”调的。

切换到真实 power share 后分布会不同。

---

# 89. 做一个 feature audit script

至少输出测试曲库：

```text
bass_share
mid_share
high_share
```

的：

```text
P10/P50/P90
```

---

# 90. 然后再定：

```text
reactor
vortex
pulse
```

global prior threshold。

---

# 91. VisualDNA prior 仍应该是弱 prior

即使 raw share 正确：

```text
structure_type
```

也不要再次变成主宰。

当前 GeometryControl 已经能 morph，

保持。

---

# 92. P1：Renderer deterministic imports 现在已经接入 grain

这是好事。

继续沿用同一：

```text
deterministic.py
```

---

# 93. 不要另外建立 Renderer RNG class

没有必要。

---

# 94. P1：RingLayer 仍手写 XOR hash

当前：

```python
track_seed ^ ring*... ^ epoch*...
```

这可以工作。

---

# 95. 但长期最好统一到 deterministic helper

理由不是安全性，

而是：

```text
可测试
可读
统一 stream namespace
```

---

# 96. Round 6 可以顺手改

例如：

```python
h_val = deterministic_float(
    track_seed,
    "ring_damage",
    damage_epoch,
    ring,
)
```

---

# 97. P2：真实视觉验收应该开始

如果 Round 6 把上述 P0 修完，

我建议不要再立刻开 Round 7 大架构。

---

# 98. 应该进入真实音乐测试

选：

```text
1. sparse piano
2. vocal pop
3. EDM
4. rock/metal
5. ambient
6. acoustic
7. noisy/industrial
```

---

# 99. 每首导出 30~60 秒 representative segment

而不是完整歌。

---

# 100. 验收三个问题

---

## Q1：不同歌曲是否仍像“同一个模板”？

重点看：

```text
主体 topology
geometry density
circulation
fragmentation
annealing
```

而不是颜色。

---

## Q2：同一首歌不同段落是否有结构历史？

例如：

```text
quiet
→ build-up
→ climax
→ recovery
```

---

## Q3：同一时刻重复 export 是否稳定？

特别：

```text
particles
spikes
camera shake
```

---

# 101. 如果视觉已经足够异质

下一步才值得做：

```text
Chladni-like nodal modes
```

---

# 102. 如果仍然同质

先不要加 Chladni。

先看：

```text
GeometryControl dynamic range
```

是不是实际太窄。

---

# 103. 加 debug trajectory plot

输出：

```text
symmetry
coherence
circulation
fragmentation
roughness
angular_lock
```

---

# 104. 如果全部长期在：

```text
0.4~0.6
```

当然看起来差不多。

---

# 105. 此时调 Material-to-Geometry mapping

不是加新效果。

---

# 106. Round 6 建议实施顺序

---

## R6-0：修 Global band semantics

1. extractor global stats 接 `band_shares`；
2. activity-weighted global share；
3. global bass/mid/high ratio；
4. thresholds 重新 audit；
5. tests。

---

## R6-1：完成 fast-event causality

1. Scene 同时读取 crossed beat + onset；
2. fast onset spark 改 crossed onset；
3. continuous onset envelope 保留给 slow path；
4. tests。

---

## R6-2：完整 track-keyed Scene determinism

1. Scene 取得 `track_seed`；
2. emit / emit_burst 都传；
3. onset spark origin deterministic；
4. ambient emission decision deterministic；
5. dt-aware emission rate。

---

## R6-3：Effects determinism

1. camera shake keyed；
2. event key；
3. remove visual global random。

---

## R6-4：Renderer determinism

1. high-frequency spike angles/radii keyed；
2. initial grain deterministic；
3. remove `import random` if possible；
4. repeat-frame test。

---

## R6-5：Strengthen rebuild/export tests

1. real DynamicsBundle fixture；
2. real particle warmup；
3. repeated seek same target；
4. segment first-frame compare；
5. decide whether fixed-step is actually needed.

---

## R6-6：Docs

1. README cache v6；
2. technical doc architecture；
3. accurate terminology；
4. remove stale v4 statements。

---

# 107. 推荐 commit 划分

```text
commit 1
fix(analysis): derive global spectral ratios from raw band power shares

commit 2
test(analysis): verify raw-share global semantics and structure priors

commit 3
fix(events): use crossed onset events for fast transient triggering

commit 4
feat(random): pass track seed through all Scene particle emissions

commit 5
feat(random): make ambient spawn and camera shake deterministic

commit 6
feat(renderer): remove remaining frame-level global randomness

commit 7
test(v2): verify Scene-level determinism and real rebuild behavior

commit 8
docs(v2): update cache v6 and final runtime architecture
```

---

# 108. 本轮不建议再修改的核心模块

除非测试失败：

```text
MaterialStateEngine
MaterialTrajectoryCompiler
AnalyticalPESField
L3 window generation
GeometryControl dataclass
```

这些已经不是主要问题。

---

# 109. 本轮也不要继续扩充 Generative Structure 大效果

目前四种 basis 都已经吃 GeometryControl。

先看真实视频效果。

---

# 110. 当前项目最重要的工程风险已经从“架构”转变为“行为一致性”

此前我们担心：

```text
新系统没接
```

现在已经不是主要问题。

---

# 111. 现在更应该担心：

```text
语义是否真的一致
随机是否真的可重建
真实视觉动态范围是否足够
```

---

# 112. 当前完成度更新

| 子系统 | Round 5 HEAD |
|---|---|
| Causal L3 | ✅ |
| L3 interpolation | ✅ |
| Material trajectory | ✅ |
| L3/L4 → Material | ✅ |
| Analytical PES | ✅ |
| GeometryControl → Ring | ✅ |
| GeometryControl → Generative Structure | ✅ |
| GeometryControl → Transient Lattice | ✅ |
| Harmonic shell material coupling | ✅ / 可继续增强 |
| Continuous defect healing | ✅ |
| Raw band shares computation | ✅ |
| Raw band shares → VisualContext tilt | ✅ |
| Raw band shares → Global ratios | ❌ |
| Cache v6 | ✅ |
| Crossed beat event | ✅ |
| Crossed onset event API | ✅ |
| Crossed onset used by Scene | ❌ |
| Particle property determinism | ✅ |
| Scene particle placement determinism | ❌ |
| Scene ambient emission determinism | ❌ |
| Effect camera shake determinism | ❌ |
| Renderer grain determinism | ✅ after track info |
| Renderer high-frequency spikes deterministic | ❌ |
| Warmup ownership | ✅ largely centralized |
| Strict seek==sequential determinism | 🟡 not proven |
| Serial/parallel raw-frame equivalence | 🟡 not proven |
| Tests quality | 🟢 much improved, still missing end-to-end cases |

---

# 113. 最终结论

Round 5 不是失败。

相反：

> **这是第一次我认为 Stormy-Pulse V2 的主体架构基本已经成型。**

现在不应该继续做：

```text
Round 6 大规模架构重构
```

而应：

> **补完最后几处语义/确定性漏洞，然后进入真实视觉评价。**

---

# 114. 给开发 Agent 的最终执行摘要

当前 `fb12c66` 已经真正完成：

```text
MaterialState
    ↓
GeometryControl
    ↓
Ring / Generative Structure / Transient Lattice
```

并且：

```text
raw band shares
causal event API
deterministic particle property generation
central rebuild ownership
```

也已经存在。

Round 6 不要新增新物理系统。

只修以下关键尾巴：

```text
1. Global bass/mid/high ratio 必须真正使用 raw band_shares
2. Scene onset fast event 必须真正使用 crossed["onset"]
3. 所有 Scene particle emit/emit_burst 必须传 track_seed
4. Scene ambient spawn / onset positions 去掉 global random
5. EffectState camera shake 去掉 global random
6. Renderer high-frequency spikes 去掉 global random
7. 强化 end-to-end tests，证明真实 Scene/Renderer 路径 deterministic
8. 用真实 songs 做视觉差异验收
```

---

# 115. Round 6 最终验收句

只有下面这句话完全成立后，基础架构阶段才建议正式结束：

> **Stormy-Pulse derives both local and global spectral semantics from correctly scaled audio features, uses strictly causal beat/onset events for fast visuals, continuously morphs its main geometry from the history-dependent material state, and reconstructs track-keyed visual randomness consistently across playback, seeking and export.**

达到这个状态后：

> **停止基础架构 round-based 重构，开始真正做视觉审美评估与效果深化。**

下一阶段才考虑：

```text
Chladni / nodal resonance
GPU shader refinement
more sophisticated defect geometry
```

而不是现在继续加。
