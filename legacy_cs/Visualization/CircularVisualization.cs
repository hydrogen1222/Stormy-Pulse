using System;
using System.Windows;
using System.Windows.Media;

namespace 音频可视化.Visualization;

public class CircularVisualization : BaseVisualization
{
    private double[] _ringRadii = new double[16];
    private double[] _ringPhases = new double[16];
    private double[] _ringThickness = new double[16];
    private double[] _ringChaos = new double[16];
    private double _bassPulse;
    private double _overallPulse;
    private double _time;
    private double _rotationAngle;
    private double _beatFlash;
    private double _transientShakeX;
    private double _transientShakeY;
    private int[] _brokenRings;

    public CircularVisualization()
    {
        _brokenRings = new int[16];
    }

    public override void Render(DrawingContext dc, Rect bounds)
    {
        if (Bands.Length == 0) return;

        _time += 0.016;
        double centerX = bounds.Width / 2;
        double centerY = bounds.Height / 2;
        double maxRadius = Math.Min(bounds.Width, bounds.Height) * 0.42;

        _bassPulse += (BassLevel * 3.0 - _bassPulse) * 0.1;
        _overallPulse += (OverallLevel * 2.5 - _overallPulse) * 0.08;

        if (OnBeat > 0.3 || TransientStrength > 0.4)
        {
            _beatFlash = 1.0;
            _transientShakeX = (Random.NextDouble() - 0.5) * TransientStrength * 15 + OnBeat * 10 * (Random.NextDouble() - 0.5);
            _transientShakeY = (Random.NextDouble() - 0.5) * TransientStrength * 10 + OnBeat * 8 * (Random.NextDouble() - 0.5);
        }
        _beatFlash *= 0.88;
        _transientShakeX *= 0.85;
        _transientShakeY *= 0.85;

        double chaosRotation = 1.0 + ChaosFactor * 3.0 + BeatStrength * 2.0;
        _rotationAngle += (0.002 + BassLevel * 0.008) * chaosRotation;

        DrawBackgroundEffect(dc, bounds, centerX + _transientShakeX, centerY + _transientShakeY, maxRadius);
        DrawOuterGlow(dc, centerX + _transientShakeX, centerY + _transientShakeY, maxRadius);

        for (int i = 0; i < _brokenRings.Length; i++)
        {
            if (ChaosFactor > 0.4 && Random.NextDouble() < ChaosFactor * 0.05)
            {
                _brokenRings[i] = _brokenRings[i] == 0 ? (int)(Random.NextDouble() * 20 + 5) : 0;
            }
            if (_brokenRings[i] > 0) _brokenRings[i]--;
        }

        int ringCount = 14 + (int)(ChaosFactor * 4);
        for (int ring = 0; ring < ringCount; ring++)
        {
            int bandIndex = ring * (Bands.Length / Math.Max(1, ringCount));
            bandIndex = Math.Min(bandIndex, Bands.Length - 1);

            float bandValue = bandIndex >= 0 && bandIndex < Bands.Length ? Bands[bandIndex] : 0;
            double amplifiedValue = Math.Max(bandValue, 0.05);

            _ringChaos[ring] += ((Random.NextDouble() - 0.5) * ChaosFactor * 0.3 - _ringChaos[ring]) * 0.1;

            double baseRadius = maxRadius * (ring + 1) / ringCount;
            double transientBoost = 1.0 + TransientStrength * 1.5 * (Random.NextDouble() > 0.8 ? 1 : 0);
            double chaosBoost = 1.0 + ChaosFactor * 0.6 * (Random.NextDouble() - 0.5);
            double targetRadius = baseRadius + amplifiedValue * maxRadius * 0.5 * chaosBoost + _bassPulse * 15 * transientBoost;

            _ringRadii[ring] += (targetRadius - _ringRadii[ring]) * 0.08;

            double phaseSpeed = 0.005 + ring * 0.0006 + BassLevel * 0.002;
            phaseSpeed *= chaosRotation;
            _ringPhases[ring] += phaseSpeed;

            double thicknessTarget = 4 + amplifiedValue * 18 + BeatPulse * 12 + ChaosFactor * 8 + BeatStrength * 15;
            thicknessTarget *= (1.0 + _ringChaos[ring]);
            _ringThickness[ring] += (thicknessTarget - _ringThickness[ring]) * 0.12;

            double hueJitter = ChaosFactor * 80 * (Random.NextDouble() - 0.5);
            double hueBeatShift = BeatPulse * 40;
            double hue = 180 + ring * 18 + Math.Sin(_time * 1.2 + ring * 0.4) * 35 + hueJitter + hueBeatShift;

            double saturation = 0.4 + amplifiedValue * 0.5 + ChaosFactor * 0.2;
            double brightness = 0.5 + amplifiedValue * 0.5 + _beatFlash * 0.3;

            Color ringColor = HsvToColor(hue, saturation, brightness);
            Color glowColor = HsvToColor(hue, saturation * 0.2, Math.Min(brightness + 0.4, 1.3), 0.8);

            double thickness = _ringThickness[ring];
            double ringPhase = _ringPhases[ring];

            DrawWavyRing(dc, centerX + _transientShakeX, centerY + _transientShakeY, _ringRadii[ring], thickness, ringColor, glowColor, bandIndex, ringPhase, ring);

            if (amplifiedValue > 0.15 && ring % (2 - (int)(ChaosFactor)) == 0)
            {
                DrawRingParticles(dc, centerX + _transientShakeX, centerY + _transientShakeY, _ringRadii[ring], hue, amplifiedValue, ringPhase, ring);
            }
        }

        DrawCenterCore(dc, centerX + _transientShakeX, centerY + _transientShakeY);
        DrawCenterWaveform(dc, centerX + _transientShakeX, centerY + _transientShakeY, maxRadius * 0.25);

        if (_beatFlash > 0.6)
        {
            var flashBrush = new SolidColorBrush(Color.FromArgb((byte)(_beatFlash * 50), 150, 180, 255));
            dc.DrawRectangle(flashBrush, null, new Rect(0, 0, bounds.Width, bounds.Height));
        }
    }

    private void DrawBackgroundEffect(DrawingContext dc, Rect bounds, double centerX, double centerY, double maxRadius)
    {
        double bgChaos = ChaosFactor * 0.3 * (Random.NextDouble() - 0.5);
        var bgGradient = new RadialGradientBrush
        {
            GradientOrigin = new Point(0.5 + bgChaos, 0.5 + bgChaos),
            Center = new Point(0.5, 0.5),
            RadiusX = 0.5,
            RadiusY = 0.5,
            GradientStops = new GradientStopCollection
            {
                new GradientStop(Color.FromArgb((byte)(40 + BeatPulse * 20), (byte)(40 + ChaosFactor * 30), (byte)(60 + ChaosFactor * 20), 120), 0),
                new GradientStop(Color.FromArgb((byte)(20 + TransientStrength * 15), 20, 30, 80), 0.5),
                new GradientStop(Color.FromArgb(0, 15, 15, 26), 1)
            }
        };
        dc.DrawEllipse(bgGradient, null, new Point(centerX, centerY), maxRadius * 1.5, maxRadius * 1.5);

        double outerGlowRadius = maxRadius * 1.2 + _bassPulse * 35 + _beatFlash * 20;
        var outerGlow = new RadialGradientBrush
        {
            GradientOrigin = new Point(0.5, 0.5),
            Center = new Point(0.5, 0.5),
            RadiusX = 0.5,
            RadiusY = 0.5,
            GradientStops = new GradientStopCollection
            {
                new GradientStop(Color.FromArgb((byte)(_bassPulse * 35 + _beatFlash * 20), (byte)(80 + _beatFlash * 50), 120, 255), 0.7),
                new GradientStop(Color.FromArgb(0, 60, 80, 200), 1)
            }
        };
        dc.DrawEllipse(outerGlow, null, new Point(centerX, centerY), outerGlowRadius, outerGlowRadius * 0.5);
    }

    private void DrawOuterGlow(DrawingContext dc, double centerX, double centerY, double maxRadius)
    {
        int glowLayers = 4 + (int)(ChaosFactor * 2);
        for (int i = glowLayers; i >= 0; i--)
        {
            double radius = maxRadius * 1.1 + i * 18 + _bassPulse * 12 + (Random.NextDouble() - 0.5) * i * ChaosFactor * 3;
            double alpha = 0.12 - i * 0.02 + _beatFlash * 0.05;

            var glowBrush = new RadialGradientBrush
            {
                GradientOrigin = new Point(centerX, centerY),
                Center = new Point(centerX, centerY),
                RadiusX = 0.5,
                RadiusY = 0.5,
                GradientStops = new GradientStopCollection
                {
                    new GradientStop(Color.FromArgb(0, 100, 150, 255), 0.6),
                    new GradientStop(Color.FromArgb((byte)(Math.Max(0, alpha) * 255), 100, 150, 255), 0.85),
                    new GradientStop(Color.FromArgb(0, 100, 150, 255), 1)
                }
            };
            dc.DrawEllipse(glowBrush, null, new Point(centerX, centerY), radius, radius * 0.5);
        }
    }

    private void DrawWavyRing(DrawingContext dc, double centerX, double centerY, double radius, double thickness, Color ringColor, Color glowColor, int bandIndex, double phase, int ring)
    {
        int segments = 180;
        var ringGeometry = new StreamGeometry();

        using (var ctx = ringGeometry.Open())
        {
            bool first = true;

            for (int i = 0; i <= segments; i++)
            {
                if (_brokenRings[ring % 16] > 0 && i % 15 < 3)
                {
                    if (!first)
                    {
                        ctx.LineTo(new Point(centerX + Math.Cos((i / (double)segments) * Math.PI * 2 + phase + _rotationAngle) * (radius + thickness),
                            centerY + Math.Sin((i / (double)segments) * Math.PI * 2 + phase + _rotationAngle) * (radius + thickness) * 0.5), false, false);
                        first = true;
                    }
                    continue;
                }

                double angle = (i / (double)segments) * Math.PI * 2 + phase + _rotationAngle;
                double wave = 1.0;

                if (bandIndex < Bands.Length)
                {
                    int waveIndex = (i * Bands.Length / segments) % Bands.Length;
                    wave = 1.0 + Bands[waveIndex] * 0.25;
                    wave += ChaosFactor * 0.15 * (Random.NextDouble() - 0.5);
                }

                double r = radius * wave;
                double x = centerX + Math.Cos(angle) * r;
                double y = centerY + Math.Sin(angle) * r * 0.5;

                if (first)
                {
                    ctx.BeginFigure(new Point(x, y), true, true);
                    first = false;
                }
                else
                {
                    ctx.LineTo(new Point(x, y), true, true);
                }
            }
        }

        ringGeometry.Freeze();

        var gradientBrush = new LinearGradientBrush
        {
            StartPoint = new Point(0, 0),
            EndPoint = new Point(1, 1),
            GradientStops = new GradientStopCollection
            {
                new GradientStop(glowColor, 0),
                new GradientStop(ringColor, 0.5),
                new GradientStop(glowColor, 1)
            }
        };

        dc.DrawGeometry(gradientBrush, null, ringGeometry);
    }

    private void DrawRingParticles(DrawingContext dc, double centerX, double centerY, double radius, double hue, double intensity, double phase, int ring)
    {
        int peakCount = 10 + (int)(ChaosFactor * 8);
        for (int p = 0; p < peakCount; p++)
        {
            int peakIdx = (p * Bands.Length / peakCount) % Math.Max(1, Bands.Length);
            float peakVal = peakIdx < Bands.Length ? Bands[peakIdx] : 0;

            if (peakVal > 0.12 || (ChaosFactor > 0.3 && Random.NextDouble() < ChaosFactor * 0.3))
            {
                double angle = (p / (double)peakCount) * Math.PI * 2 + phase + _rotationAngle;
                angle += ChaosFactor * 0.2 * (Random.NextDouble() - 0.5);
                double px = centerX + Math.Cos(angle) * radius;
                double py = centerY + Math.Sin(angle) * radius * 0.5;

                double particleSize = 4 + peakVal * 14 + _beatFlash * 6;

                for (int g = 2; g >= 0; g--)
                {
                    var particleBrush = new RadialGradientBrush
                    {
                        GradientOrigin = new Point(0.5, 0.5),
                        Center = new Point(0.5, 0.5),
                        RadiusX = 0.5,
                        RadiusY = 0.5,
                        GradientStops = new GradientStopCollection
                        {
                            new GradientStop(Colors.White, 0),
                            new GradientStop(HsvToColor(hue + 50 + _beatFlash * 30, 0.2, 1.3), 0.3),
                            new GradientStop(HsvToColor(hue + 30, 0.4, 1.1, 0.6), 0.7),
                            new GradientStop(Color.FromArgb(0, 0, 0, 0), 1)
                        }
                    };
                    dc.DrawEllipse(particleBrush, null, new Point(px, py), particleSize + g * 5, (particleSize + g * 5) * 0.5);
                }
            }
        }
    }

    private void DrawCenterCore(DrawingContext dc, double centerX, double centerY)
    {
        double coreRadius = 20 + _bassPulse * 80 + _beatFlash * 40;
        coreRadius *= (1.0 + ChaosFactor * 0.3);

        for (int g = 5; g >= 0; g--)
        {
            double glowRadius = coreRadius + g * 18;
            double alpha = 0.35 - g * 0.05 + _beatFlash * 0.1;

            var coreGlow = new RadialGradientBrush
            {
                GradientOrigin = new Point(0.5, 0.5),
                Center = new Point(0.5, 0.5),
                RadiusX = 0.5,
                RadiusY = 0.5,
                GradientStops = new GradientStopCollection
                {
                    new GradientStop(Colors.White, 0),
                    new GradientStop(Color.FromArgb((byte)(alpha * 255), 150, 200, 255), 0.3),
                    new GradientStop(Color.FromArgb((byte)(alpha * 200), 100, 150, 255), 0.6),
                    new GradientStop(Color.FromArgb((byte)(alpha * 100), 80, 120, 200), 0.85),
                    new GradientStop(Color.FromArgb(0, 0, 0, 0), 1)
                }
            };
            dc.DrawEllipse(coreGlow, null, new Point(centerX, centerY), glowRadius, glowRadius * 0.5);
        }
    }

    private void DrawCenterWaveform(DrawingContext dc, double centerX, double centerY, double radius)
    {
        if (Bands.Length < 4) return;

        int points = Math.Min(Bands.Length, 128);
        var waveformGeometry = new StreamGeometry();

        using (var ctx = waveformGeometry.Open())
        {
            bool first = true;

            for (int i = 0; i < points; i++)
            {
                int bandIdx = (i * Bands.Length / points) % Bands.Length;
                float value = bandIdx < Bands.Length ? Bands[bandIdx] : 0;

                double chaosOffset = ChaosFactor * 0.2 * (Random.NextDouble() - 0.5);
                double angle = (i / (double)points) * Math.PI * 2 - Math.PI / 2 + _rotationAngle + chaosOffset;
                double r = radius * (0.3 + value * 1.5);

                double x = centerX + Math.Cos(angle) * r;
                double y = centerY + Math.Sin(angle) * r * 0.5;

                if (first)
                {
                    ctx.BeginFigure(new Point(x, y), false, false);
                    first = false;
                }
                else
                {
                    ctx.LineTo(new Point(x, y), true, false);
                }
            }
        }

        waveformGeometry.Freeze();

        var waveformPen = new Pen(new SolidColorBrush(Color.FromArgb((byte)(150 + _beatFlash * 50), 200, 230, 255)), 2 + _beatFlash);
        dc.DrawGeometry(null, waveformPen, waveformGeometry);
    }
}