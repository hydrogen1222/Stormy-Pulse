using System;
using System.Windows;
using System.Windows.Media;

namespace 音频可视化.Visualization;

public class BarVisualization : BaseVisualization
{
    private const int BarCount = 64;
    private double[] _barHeights = new double[BarCount];
    private double[] _targetHeights = new double[BarCount];
    private double[] _peakHeights = new double[BarCount];
    private double[] _peakDecay = new double[BarCount];
    private double[] _individualPhases = new double[BarCount];
    private double[] _chaosOffsets = new double[BarCount];
    private double _globalPulse;
    private double _time;
    private double[] _glowIntensities = new double[BarCount];
    private double _bassJitter;
    private double _beatFlash;

    public override void Render(DrawingContext dc, Rect bounds)
    {
        if (Bands.Length == 0) return;

        _time += 0.016;
        double centerY = bounds.Height / 2;
        int barsToShow = Math.Min(BarCount, Bands.Length);
        double barWidth = bounds.Width / barsToShow - 4;
        double maxHeight = bounds.Height * 0.72;

        _globalPulse += (BassLevel * 2.5 - _globalPulse) * 0.15;
        _bassJitter += (ChaosFactor * 8 - _bassJitter) * 0.3;

        if (OnBeat > 0.3 || TransientStrength > 0.4)
        {
            _beatFlash = 1.0;
        }
        _beatFlash *= 0.88;

        double beatKick = BeatStrength * 1.5f;
        double beatPhaseEffect = Math.Sin(BeatPhase * Math.PI * 2) * 0.5 + 0.5;

        DrawBackgroundGrid(dc, bounds);

        for (int i = 0; i < barsToShow; i++)
        {
            if (_individualPhases[i] == 0)
                _individualPhases[i] = Random.NextDouble() * Math.PI * 2;

            double bandValue = Math.Max(Bands[i], 0.03);

            double chaosMultiplier = 1.0 + ChaosFactor * 0.5 * (Random.NextDouble() - 0.5);
            double transientBoost = 1.0 + TransientStrength * 2.5 * (Random.NextDouble() > 0.6 ? 1 : 0);
            double beatBoost = 1.0 + beatKick * (0.5 + Random.NextDouble() * 0.5);
            _targetHeights[i] = bandValue * maxHeight * chaosMultiplier * transientBoost * beatBoost;

            double interpSpeed = 0.15 + BeatPulse * 0.5 + OnBeat * 0.3;
            interpSpeed = Math.Min(interpSpeed, 0.6);
            _barHeights[i] += (_targetHeights[i] - _barHeights[i]) * interpSpeed;

            if (_barHeights[i] > _peakHeights[i])
            {
                _peakHeights[i] = _barHeights[i];
                _peakDecay[i] = 0;
            }
            else
            {
                _peakDecay[i] += 0.02 + beatKick * 0.03;
                _peakHeights[i] -= _peakDecay[i] * _peakHeights[i] * 0.1;
                if (ChaosFactor > 0.3 && Random.NextDouble() < ChaosFactor * 0.1)
                {
                    _peakHeights[i] *= 0.95;
                }
                _peakHeights[i] = Math.Max(_peakHeights[i], _barHeights[i] * 0.5);
            }

            double x = i * (barWidth + 4) + 2;

            double hueShift = Math.Sin(_time * 3 + i * 0.2 + _individualPhases[i]) * 30;
            hueShift += ChaosFactor * 60 * (Random.NextDouble() - 0.5);
            hueShift += BeatPulse * 20 + OnBeat * 40;
            hueShift += SpectralCentroid * 10 * (Random.NextDouble() - 0.5);
            double hue = 180 + (i / (double)barsToShow) * 180 + hueShift;

            double barHeight = Math.Max(_barHeights[i], 4);
            double peakHeight = Math.Max(_peakHeights[i], 4);

            double jitterX = ChaosFactor > 0.4 ? (Random.NextDouble() - 0.5) * 4 * ChaosFactor : 0;
            double jitterY = TransientStrength > 0.2 ? (Random.NextDouble() - 0.5) * 6 * TransientStrength : 0;

            double baseGlow = bandValue * 3.0 + BeatPulse * 2.0 + beatKick * 3.0 + OnBeat * 2.0;
            _glowIntensities[i] += (baseGlow - _glowIntensities[i]) * 0.25;

            if (_glowIntensities[i] > 0.1)
            {
                int glowLayers = 3 + (int)(ChaosFactor * 2) + (int)(beatKick * 2);
                for (int g = glowLayers; g >= 1; g--)
                {
                    double glowAlpha = _glowIntensities[i] * 25 / g;
                    glowAlpha *= 1.0 + (Random.NextDouble() - 0.5) * ChaosFactor * 0.3;
                    glowAlpha = Math.Min(glowAlpha, 0.5);
                    double glowWidth = barWidth + g * 14 + _bassJitter * g;
                    double glowHeight = barHeight + g * 10 + _bassJitter * 2;
                    Color glowColor = HsvToColor(hue + g * 15 * ChaosFactor, 0.4 + ChaosFactor * 0.2, 1.0);

                    var glowBrush = new RadialGradientBrush
                    {
                        GradientOrigin = new Point(0.5, 0.5),
                        Center = new Point(0.5, 0.5),
                        RadiusX = 0.5,
                        RadiusY = 0.5,
                        GradientStops = new GradientStopCollection
                        {
                            new GradientStop(Color.FromArgb((byte)(glowAlpha * 255), glowColor.R, glowColor.G, glowColor.B), 0.3),
                            new GradientStop(Colors.Transparent, 1)
                        }
                    };
                    dc.DrawRectangle(glowBrush, null, new Rect(x + jitterX - g * 6, centerY - glowHeight / 2 + jitterY, glowWidth, glowHeight));
                }
            }

            Color topColor = HsvToColor(hue, 0.5 + ChaosFactor * 0.2, 1.0 + BeatPulse * 0.2 + beatKick * 0.3);
            Color midColor = HsvToColor(hue + 30, 0.6 + ChaosFactor * 0.2, 0.85);
            Color bottomColor = HsvToColor(hue + 60, 0.7 + ChaosFactor * 0.2, 0.65);

            var topGradient = new LinearGradientBrush
            {
                StartPoint = new Point(0, 0),
                EndPoint = new Point(0, 1),
                GradientStops = new GradientStopCollection
                {
                    new GradientStop(Colors.White, 0),
                    new GradientStop(topColor, 0.3),
                    new GradientStop(midColor, 0.7),
                    new GradientStop(bottomColor, 1.0)
                }
            };
            dc.DrawRectangle(topGradient, null, new Rect(x + jitterX, centerY - barHeight / 2 + jitterY, barWidth, barHeight / 2));

            var bottomGradient = new LinearGradientBrush
            {
                StartPoint = new Point(0, 0),
                EndPoint = new Point(0, 1),
                GradientStops = new GradientStopCollection
                {
                    new GradientStop(bottomColor, 0.0),
                    new GradientStop(midColor, 0.5),
                    new GradientStop(Color.FromArgb(150, topColor.R, topColor.G, topColor.B), 1.0)
                }
            };
            dc.DrawRectangle(bottomGradient, null, new Rect(x + jitterX, centerY + jitterY, barWidth, barHeight / 2));

            if (peakHeight > 15)
            {
                double peakY = centerY - peakHeight / 2 - 4 + jitterY;
                double peakChaos = ChaosFactor * 0.5 + (Random.NextDouble() - 0.5) * 0.2;
                Color peakColor = HsvToColor(hue + 20 + peakChaos * 30, 0.2, 1.3 + beatKick * 0.3);
                double peakSizeVar = 1.0 + ChaosFactor * 0.3 * (Random.NextDouble() - 0.5) + beatKick * 0.2;

                var peakBrush = new RadialGradientBrush
                {
                    GradientOrigin = new Point(0.5, 0.5),
                    Center = new Point(0.5, 0.5),
                    RadiusX = 0.5,
                    RadiusY = 0.5,
                    GradientStops = new GradientStopCollection
                    {
                        new GradientStop(Colors.White, 0),
                        new GradientStop(peakColor, 0.5),
                        new GradientStop(Colors.Transparent, 1)
                    }
                };
                dc.DrawEllipse(peakBrush, null, new Point(x + barWidth / 2 + jitterX, peakY), (barWidth / 2 + 4) * peakSizeVar, 6 * peakSizeVar);
            }

            double reflectionHeight = barHeight * 0.4;
            double reflectionY = centerY + barHeight / 2 + 4;
            var reflectionBrush = new LinearGradientBrush
            {
                StartPoint = new Point(0, 0),
                EndPoint = new Point(0, 1),
                GradientStops = new GradientStopCollection
                {
                    new GradientStop(Color.FromArgb((byte)(60 * _beatFlash + 30), bottomColor.R, bottomColor.G, bottomColor.B), 0),
                    new GradientStop(Color.FromArgb(10, bottomColor.R, bottomColor.G, bottomColor.B), 0.5),
                    new GradientStop(Colors.Transparent, 1)
                }
            };
            dc.DrawRectangle(reflectionBrush, null, new Rect(x + jitterX, reflectionY + jitterY, barWidth, reflectionHeight));

            if ((ChaosFactor > 0.5 || beatKick > 0.3) && Random.NextDouble() < (ChaosFactor * 0.1 + beatKick * 0.15) && barHeight > 30)
            {
                double sparkX = x + Random.NextDouble() * barWidth;
                double sparkY = centerY - barHeight / 2 + Random.NextDouble() * barHeight;
                double sparkSize = 2 + Random.NextDouble() * 4 + beatKick * 3;

                var sparkBrush = new RadialGradientBrush
                {
                    GradientOrigin = new Point(0.5, 0.5),
                    Center = new Point(0.5, 0.5),
                    RadiusX = 0.5,
                    RadiusY = 0.5,
                    GradientStops = new GradientStopCollection
                    {
                        new GradientStop(Colors.White, 0),
                        new GradientStop(Color.FromArgb(200, 255, 255, 200), 0.4),
                        new GradientStop(Colors.Transparent, 1)
                    }
                };
                dc.DrawEllipse(sparkBrush, null, new Point(sparkX, sparkY), sparkSize, sparkSize);
            }
        }

        double lineGlow = 0.3 + _globalPulse * 0.5 + _beatFlash * 0.3 + beatKick * 0.4;
        double flashIntensity = 1.0 + _beatFlash * 2.0 + beatKick;

        var centerLineBrush = new LinearGradientBrush
        {
            StartPoint = new Point(0, 0),
            EndPoint = new Point(1, 0),
            GradientStops = new GradientStopCollection
            {
                new GradientStop(Colors.Transparent, 0),
                new GradientStop(Color.FromArgb((byte)(lineGlow * 100 * flashIntensity), 100, 150, 255), 0.2),
                new GradientStop(Color.FromArgb((byte)(lineGlow * 150 * flashIntensity), 150, 200, 255), 0.5),
                new GradientStop(Color.FromArgb((byte)(lineGlow * 100 * flashIntensity), 100, 150, 255), 0.8),
                new GradientStop(Colors.Transparent, 1)
            }
        };
        dc.DrawRectangle(centerLineBrush, null, new Rect(0, centerY - 1, bounds.Width, 2));

        if (_beatFlash > 0.5 || beatKick > 0.3)
        {
            var flashBrush = new SolidColorBrush(Color.FromArgb((byte)(Math.Max(_beatFlash, beatKick) * 50), 200, 220, 255));
            dc.DrawRectangle(flashBrush, null, new Rect(0, 0, bounds.Width, bounds.Height));
        }
    }

    private void DrawBackgroundGrid(DrawingContext dc, Rect bounds)
    {
        double centerY = bounds.Height / 2;
        int lines = 12;
        double spacing = bounds.Height / lines;

        for (int i = 0; i <= lines; i++)
        {
            double y = i * spacing;
            double alpha = (1 - Math.Abs(y - centerY) / (bounds.Height / 2)) * (0.3 + ChaosFactor * 0.2);
            double chaosOffset = ChaosFactor > 0.3 ? (Random.NextDouble() - 0.5) * 4 * ChaosFactor : 0;

            byte r = (byte)(80 + ChaosFactor * 40);
            byte g = (byte)(100 + ChaosFactor * 30);
            byte b = (byte)(150 + ChaosFactor * 50);
            var pen = new Pen(new SolidColorBrush(Color.FromArgb((byte)(alpha * 25), r, g, b)), 1);
            dc.DrawLine(pen, new Point(chaosOffset, y), new Point(bounds.Width + chaosOffset, y));
        }
    }
}