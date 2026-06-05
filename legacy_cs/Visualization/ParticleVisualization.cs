using System;
using System.Collections.Generic;
using System.Linq;
using System.Windows;
using System.Windows.Media;

namespace 音频可视化.Visualization;

public class Particle
{
    public double X { get; set; }
    public double Y { get; set; }
    public double VelocityX { get; set; }
    public double VelocityY { get; set; }
    public double Size { get; set; }
    public double Life { get; set; }
    public double MaxLife { get; set; }
    public double Hue { get; set; }
    public double Decay { get; set; }
    public double TrailLength { get; set; }
    public List<Point> Trail { get; set; } = new();
    public bool IsSpark { get; set; }
    public double Rotation { get; set; }
    public double Spin { get; set; }
}

public class ParticleVisualization : BaseVisualization
{
    private List<Particle> _particles = new();
    private const int MaxParticles = 1500;
    private double _bassPulse;
    private double _midPulse;
    private double _time;
    private double _vortexAngle;
    private double _beatFlash;
    private double _transientExplosion;
    private double _shockwaveRadius;
    private bool _shockwaveActive;

    public override void Render(DrawingContext dc, Rect bounds)
    {
        double centerX = bounds.Width / 2;
        double centerY = bounds.Height / 2;

        _time += 0.016;
        double vortexSpeed = 0.003 + BassLevel * 0.006 + OnBeat * 0.008 + BeatStrength * 0.01;
        _vortexAngle += vortexSpeed * (1 + ChaosFactor * 2);

        _bassPulse += (BassLevel * 4.0 - _bassPulse) * 0.18;
        _midPulse += (MidLevel * 3.0 - _midPulse) * 0.12;

        if (OnBeat > 0.4 || BeatPulse > 0.5)
        {
            _beatFlash = 1.0;
            EmitBeatBurst(centerX, centerY);
        }

        if ((OnBeat > 0.5 || TransientStrength > 0.5) && !_shockwaveActive)
        {
            _shockwaveActive = true;
            _shockwaveRadius = 0;
            _transientExplosion = Math.Max(OnBeat, TransientStrength);
        }

        if (_shockwaveActive)
        {
            _shockwaveRadius += 15 + BassLevel * 20;
            _transientExplosion *= 0.92;
            if (_transientExplosion < 0.05)
            {
                _shockwaveActive = false;
            }
        }

        _beatFlash *= 0.92;

        DrawVortexBackground(dc, bounds, centerX, centerY);

        if (_bassPulse > 0.05 && _particles.Count < MaxParticles)
        {
            int baseEmit = Math.Min((int)(_bassPulse * 30), MaxParticles - _particles.Count);
            int extraEmit = (int)(ChaosFactor * baseEmit * 0.5);
            int totalEmit = baseEmit + extraEmit;

            for (int i = 0; i < totalEmit; i++)
            {
                EmitParticle(centerX, centerY, false);
            }

            if (_bassPulse > 0.4 && _particles.Count < MaxParticles - 30)
            {
                int sparkleCount = (int)(_bassPulse * 8) + (int)(ChaosFactor * 5);
                for (int i = 0; i < sparkleCount; i++)
                {
                    EmitParticle(centerX, centerY, true);
                }
            }
        }

        if (_shockwaveActive)
        {
            DrawShockwave(dc, centerX, centerY);
        }

        foreach (var particle in _particles)
        {
            if (particle.Trail.Count > 2 && particle.Life > 0.3)
            {
                DrawParticleTrail(dc, particle);
            }
        }

        _particles = _particles.Where(p => p.Life > 0).ToList();

        foreach (var particle in _particles)
        {
            UpdateParticle(particle, bounds, centerX, centerY);

            if (particle.Life > 0.05)
            {
                DrawParticle(dc, particle);
            }
        }

        DrawConnections(dc);
        DrawCenterCore(dc, centerX, centerY);
        DrawFrequencyRings(dc, centerX, centerY);

        if (_beatFlash > 0.6)
        {
            var flashBrush = new SolidColorBrush(Color.FromArgb((byte)(_beatFlash * 60), 180, 220, 255));
            dc.DrawRectangle(flashBrush, null, new Rect(0, 0, bounds.Width, bounds.Height));
        }
    }

    private void EmitBeatBurst(double centerX, double centerY)
    {
        if (_particles.Count >= MaxParticles - 100) return;

        int burstCount = 30 + (int)(BeatPulse * 50) + (int)(ChaosFactor * 30);
        for (int i = 0; i < burstCount; i++)
        {
            double angle = (i / (double)burstCount) * Math.PI * 2;
            angle += (Random.NextDouble() - 0.5) * 0.3;

            double speed = 8 + BeatPulse * 15 + Random.NextDouble() * 8;
            double hue = 160 + Random.NextDouble() * 120 + BeatPulse * 30;

            var particle = new Particle
            {
                X = centerX,
                Y = centerY,
                VelocityX = Math.Cos(angle) * speed,
                VelocityY = Math.Sin(angle) * speed * 0.6,
                Size = 4 + BeatPulse * 15 + Random.NextDouble() * 10,
                Life = 1.0,
                MaxLife = 80 + Random.NextDouble() * 60,
                Hue = hue,
                Decay = 0.012 + Random.NextDouble() * 0.008,
                TrailLength = 20 + Random.NextDouble() * 15,
                IsSpark = false
            };

            particle.Trail.Add(new Point(particle.X, particle.Y));
            _particles.Add(particle);
        }
    }

    private void EmitParticle(double centerX, double centerY, bool isSpark)
    {
        double angle = Random.NextDouble() * Math.PI * 2;
        double spread = isSpark ? 0.2 : 0.6;
        angle += Math.Sin(_time * 3 + angle * 2) * spread;
        angle += (Random.NextDouble() - 0.5) * ChaosFactor * 0.5;

        double speed = isSpark
            ? 10 + _bassPulse * 12 + Random.NextDouble() * 8
            : 2 + _bassPulse * 12 + Random.NextDouble() * 6;

        if (BeatPulse > 0.5)
        {
            speed *= 1.5 + BeatPulse * 0.5;
        }

        double hue = isSpark
            ? 30 + Random.NextDouble() * 50
            : 160 + Random.NextDouble() * 140 + Math.Sin(_time + angle) * 40;
        hue += ChaosFactor * 60 * (Random.NextDouble() - 0.5);

        var particle = new Particle
        {
            X = centerX,
            Y = centerY,
            VelocityX = Math.Cos(angle) * speed,
            VelocityY = Math.Sin(angle) * speed * 0.6,
            Size = isSpark ? 2 + Random.NextDouble() * 5 : 3 + _bassPulse * 14 + Random.NextDouble() * 8,
            Life = 1.0,
            MaxLife = isSpark ? 30 + Random.NextDouble() * 30 : 100 + Random.NextDouble() * 100,
            Hue = hue,
            Decay = isSpark ? 0.025 + Random.NextDouble() * 0.015 : 0.006 + Random.NextDouble() * 0.01,
            TrailLength = isSpark ? 5 : 12 + Random.NextDouble() * 18,
            IsSpark = isSpark,
            Rotation = Random.NextDouble() * Math.PI * 2,
            Spin = (Random.NextDouble() - 0.5) * 0.2
        };

        particle.Trail.Add(new Point(particle.X, particle.Y));
        _particles.Add(particle);
    }

    private void DrawShockwave(DrawingContext dc, double centerX, double centerY)
    {
        double maxRadius = Math.Min(800, 1200);
        if (_shockwaveRadius > maxRadius) return;

        double alpha = _transientExplosion * 0.4;
        double thickness = 5 + _transientExplosion * 10;

        var shockwaveBrush = new RadialGradientBrush
        {
            GradientOrigin = new Point(centerX, centerY),
            Center = new Point(centerX, centerY),
            RadiusX = 0.5,
            RadiusY = 0.5,
            GradientStops = new GradientStopCollection
            {
                new GradientStop(Color.FromArgb((byte)(alpha * 255), 200, 220, 255), 0.9),
                new GradientStop(Color.FromArgb((byte)(alpha * 100), 100, 150, 255), 1)
            }
        };

        var shockwaveGeometry = new EllipseGeometry(new Point(centerX, centerY), _shockwaveRadius, _shockwaveRadius * 0.5);
        var innerGeometry = new EllipseGeometry(new Point(centerX, centerY), Math.Max(1, _shockwaveRadius - thickness), Math.Max(1, (_shockwaveRadius - thickness) * 0.5));
        var combinedGeometry = new CombinedGeometry(GeometryCombineMode.Exclude, shockwaveGeometry, innerGeometry);

        dc.DrawGeometry(shockwaveBrush, null, combinedGeometry);
    }

    private void DrawVortexBackground(DrawingContext dc, Rect bounds, double centerX, double centerY)
    {
        double maxRadius = Math.Min(bounds.Width, bounds.Height) * 0.45;

        double bgChaos = ChaosFactor * 0.4 * (Random.NextDouble() - 0.5);
        var vortexGradient = new RadialGradientBrush
        {
            GradientOrigin = new Point(0.5 + bgChaos, 0.5 + bgChaos),
            Center = new Point(0.5, 0.5),
            RadiusX = 0.5,
            RadiusY = 0.5,
            GradientStops = new GradientStopCollection
            {
                new GradientStop(Color.FromArgb((byte)(50 + BeatPulse * 30), (byte)(60 + ChaosFactor * 30), (byte)(80 + ChaosFactor * 20), 150), 0),
                new GradientStop(Color.FromArgb((byte)(30 + TransientStrength * 20), 30, 40, 100), 0.4),
                new GradientStop(Color.FromArgb((byte)(10 + _beatFlash * 20), 15, 20, 50), 0.7),
                new GradientStop(Color.FromArgb(0, 15, 15, 26), 1)
            }
        };
        dc.DrawEllipse(vortexGradient, null, new Point(centerX, centerY), maxRadius * 1.3, maxRadius * 1.3 * 0.5);

        int armCount = 3 + (int)(ChaosFactor * 2);
        for (int arm = 0; arm < armCount; arm++)
        {
            var spiralGeometry = new StreamGeometry();
            using (var ctx = spiralGeometry.Open())
            {
                int points = 100;
                bool first = true;
                for (int i = 0; i <= points; i++)
                {
                    double t = i / (double)points;
                    double angle = t * Math.PI * 4 + arm * (Math.PI * 2 / armCount) + _vortexAngle;
                    angle += ChaosFactor * 0.3 * Math.Sin(t * 10 + _time * 5);
                    double r = t * maxRadius * 0.8;
                    double x = centerX + Math.Cos(angle) * r;
                    double y = centerY + Math.Sin(angle) * r * 0.5;

                    double alpha = (1 - t) * (0.15 + _midPulse * 0.2) * (1 + ChaosFactor * 0.5);

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
            spiralGeometry.Freeze();

            var spiralPen = new Pen(new SolidColorBrush(Color.FromArgb((byte)(35 + _midPulse * 40 + ChaosFactor * 30), 100, 150, 255)), 2 + (int)(ChaosFactor * 2));
            dc.DrawGeometry(null, spiralPen, spiralGeometry);
        }

        double glowRadius = maxRadius * 1.1 + _bassPulse * 50 + _beatFlash * 30;
        for (int g = 4; g >= 0; g--)
        {
            var glowBrush = new RadialGradientBrush
            {
                GradientOrigin = new Point(centerX, centerY),
                Center = new Point(centerX, centerY),
                RadiusX = 0.5,
                RadiusY = 0.5,
                GradientStops = new GradientStopCollection
                {
                    new GradientStop(Color.FromArgb(0, 80, 120, 255), 0.5),
                    new GradientStop(Color.FromArgb((byte)(_bassPulse * 30 + _beatFlash * 20 - g * 5), 80, 120, 255), 0.8),
                    new GradientStop(Color.FromArgb(0, 80, 120, 255), 1)
                }
            };
            dc.DrawEllipse(glowBrush, null, new Point(centerX, centerY), glowRadius + g * 12, (glowRadius + g * 12) * 0.5);
        }
    }

    private void UpdateParticle(Particle particle, Rect bounds, double centerX, double centerY)
    {
        if (particle.Trail.Count > particle.TrailLength)
        {
            particle.Trail.RemoveAt(0);
        }
        particle.Trail.Add(new Point(particle.X, particle.Y));

        double dx = particle.X - centerX;
        double dy = particle.Y - centerY;
        double dist = Math.Sqrt(dx * dx + dy * dy);

        if (dist > 1)
        {
            double tangentStrength = 0.12 + ChaosFactor * 0.08 * (Random.NextDouble() - 0.5);
            double tangentX = -dy / dist * tangentStrength;
            double tangentY = dx / dist * tangentStrength * 0.5;
            particle.VelocityX += tangentX;
            particle.VelocityY += tangentY;

            double attractStrength = 0.015 + ChaosFactor * 0.01 * (Random.NextDouble() - 0.5);
            particle.VelocityX -= dx / dist * attractStrength;
            particle.VelocityY -= dy / dist * attractStrength * 0.5;

            if (BeatPulse > 0.7 && Random.NextDouble() < 0.3)
            {
                particle.VelocityX += (Random.NextDouble() - 0.5) * BeatPulse * 2;
                particle.VelocityY += (Random.NextDouble() - 0.5) * BeatPulse * 1.2;
            }
        }

        particle.X += particle.VelocityX;
        particle.Y += particle.VelocityY;

        double damping = 0.97 + ChaosFactor * 0.015 * (Random.NextDouble() - 0.5);
        particle.VelocityX *= damping;
        particle.VelocityY *= damping;

        particle.Rotation += particle.Spin * (1 + ChaosFactor);

        double decayBoost = 1.0 + ChaosFactor * 0.5;
        particle.Life -= particle.Decay * decayBoost;
        particle.Size *= 0.991;
    }

    private void DrawParticleTrail(DrawingContext dc, Particle particle)
    {
        if (particle.Trail.Count < 2) return;

        var trailGeometry = new StreamGeometry();
        using (var ctx = trailGeometry.Open())
        {
            bool first = true;
            for (int i = 0; i < particle.Trail.Count; i++)
            {
                var point = particle.Trail[i];
                double alpha = (i / (double)particle.Trail.Count) * particle.Life * 0.5;

                if (first)
                {
                    ctx.BeginFigure(point, false, false);
                    first = false;
                }
                else
                {
                    ctx.LineTo(point, true, false);
                }
            }
        }
        trailGeometry.Freeze();

        double hue = particle.Hue;
        Color trailColor = HsvToColor(hue, 0.5, 0.8, 0.4);

        var trailPen = new Pen(new SolidColorBrush(Color.FromArgb((byte)(particle.Life * 80), trailColor.R, trailColor.G, trailColor.B)), Math.Max(0.5, particle.Size * 0.25));
        dc.DrawGeometry(null, trailPen, trailGeometry);
    }

    private void DrawParticle(DrawingContext dc, Particle particle)
    {
        double alpha = Math.Min(1.0, particle.Life * 1.5);
        double saturation = particle.IsSpark ? 0.9 : 0.4 + _midPulse * 0.5;
        double brightness = particle.IsSpark ? 1.3 : 0.6 + particle.Life * 0.4;
        brightness += _beatFlash * 0.3;

        Color particleColor = HsvToColor(particle.Hue, saturation, brightness, alpha);

        int glowLayers = 3 + (int)(ChaosFactor * 2);
        for (int g = glowLayers; g >= 0; g--)
        {
            double glowSize = particle.Size + g * 7;
            double glowAlpha = alpha * (0.25 - g * 0.05);

            var glowBrush = new RadialGradientBrush
            {
                GradientOrigin = new Point(0.5, 0.5),
                Center = new Point(0.5, 0.5),
                RadiusX = 0.5,
                RadiusY = 0.5,
                GradientStops = new GradientStopCollection
                {
                    new GradientStop(Colors.White, 0),
                    new GradientStop(Color.FromArgb((byte)(glowAlpha * 255), particleColor.R, particleColor.G, particleColor.B), 0.4),
                    new GradientStop(Color.FromArgb(0, 0, 0, 0), 1)
                }
            };
            dc.DrawEllipse(glowBrush, null, new Point(particle.X, particle.Y), glowSize, glowSize * 0.5);
        }

        var coreBrush = new RadialGradientBrush
        {
            GradientOrigin = new Point(0.3, 0.3),
            Center = new Point(0.5, 0.5),
            RadiusX = 0.5,
            RadiusY = 0.5,
            GradientStops = new GradientStopCollection
            {
                new GradientStop(Colors.White, 0),
                new GradientStop(Color.FromArgb((byte)(alpha * 255), particleColor.R, particleColor.G, particleColor.B), 0.5),
                new GradientStop(Color.FromArgb(0, 0, 0, 0), 1)
            }
        };
        dc.DrawEllipse(coreBrush, null, new Point(particle.X, particle.Y), particle.Size, particle.Size * 0.5);
    }

    private void DrawConnections(DrawingContext dc)
    {
        double connectionDistance = 70 + ChaosFactor * 40;
        const double maxConnections = 200;
        int connections = 0;

        for (int i = 0; i < _particles.Count && connections < maxConnections; i++)
        {
            var p1 = _particles[i];
            if (p1.Life < 0.3) continue;

            for (int j = i + 1; j < _particles.Count && connections < maxConnections; j++)
            {
                var p2 = _particles[j];
                if (p2.Life < 0.3) continue;

                double dx = p1.X - p2.X;
                double dy = p1.Y - p2.Y;
                double dist = Math.Sqrt(dx * dx + dy * dy);

                if (dist < connectionDistance)
                {
                    double alpha = (1 - dist / connectionDistance) * Math.Min(p1.Life, p2.Life) * 0.35;
                    alpha *= (1 + _beatFlash * 0.5);

                    var connectionPen = new Pen(new SolidColorBrush(Color.FromArgb((byte)(alpha * 255), 150, 200, 255)), 1 + (int)(ChaosFactor));
                    dc.DrawLine(connectionPen, new Point(p1.X, p1.Y), new Point(p2.X, p2.Y));
                    connections++;
                }
            }
        }
    }

    private void DrawCenterCore(DrawingContext dc, double centerX, double centerY)
    {
        double coreRadius = 30 + _bassPulse * 120 + _beatFlash * 50;
        coreRadius *= (1.0 + ChaosFactor * 0.4);

        for (int g = 6; g >= 0; g--)
        {
            double glowRadius = coreRadius + g * 22;
            double alpha = 0.4 - g * 0.05 + _beatFlash * 0.08;

            var coreGlow = new RadialGradientBrush
            {
                GradientOrigin = new Point(0.5, 0.5),
                Center = new Point(0.5, 0.5),
                RadiusX = 0.5,
                RadiusY = 0.5,
                GradientStops = new GradientStopCollection
                {
                    new GradientStop(Colors.White, 0),
                    new GradientStop(Color.FromArgb((byte)(alpha * 255), 180, 220, 255), 0.2),
                    new GradientStop(Color.FromArgb((byte)(alpha * 200), 120, 180, 255), 0.5),
                    new GradientStop(Color.FromArgb((byte)(alpha * 100), 80, 140, 220), 0.8),
                    new GradientStop(Color.FromArgb(0, 0, 0, 0), 1)
                }
            };
            dc.DrawEllipse(coreGlow, null, new Point(centerX, centerY), glowRadius, glowRadius * 0.5);
        }
    }

    private void DrawFrequencyRings(DrawingContext dc, double centerX, double centerY)
    {
        if (_midPulse < 0.1 && ChaosFactor < 0.2) return;

        int ringCount = 6 + (int)(ChaosFactor * 3);
        for (int r = 0; r < ringCount; r++)
        {
            double phase = (r / (double)ringCount) * Math.PI * 2 + _time * (1.5 + ChaosFactor);
            double baseRadius = 60 + r * 45;
            double ringRadius = baseRadius + _midPulse * 80 + Math.Sin(phase) * 25 + _beatFlash * 20;
            double alpha = Math.Max(0, 0.5 - r * 0.06 - _midPulse * 0.15 - ChaosFactor * 0.1);

            if (alpha <= 0) continue;

            var ringBrush = new RadialGradientBrush
            {
                GradientOrigin = new Point(centerX, centerY),
                Center = new Point(centerX, centerY),
                RadiusX = 0.5,
                RadiusY = 0.5,
                GradientStops = new GradientStopCollection
                {
                    new GradientStop(Color.FromArgb(0, 100, 180, 255), 0.5),
                    new GradientStop(Color.FromArgb((byte)(alpha * 200), 100, 180, 255), 0.7),
                    new GradientStop(Color.FromArgb(0, 100, 180, 255), 1)
                }
            };

            var ringGeometry = new EllipseGeometry(new Point(centerX, centerY), ringRadius, ringRadius * 0.5);
            dc.DrawGeometry(ringBrush, null, ringGeometry);

            int dots = 30 + r * 8 + (int)(ChaosFactor * 20);
            for (int d = 0; d < dots; d++)
            {
                double angle = (d / (double)dots) * Math.PI * 2 + _time + r * 0.5;
                angle += ChaosFactor * 0.3 * (Random.NextDouble() - 0.5);

                int bandIdx = (d * Bands.Length / dots) % Math.Max(1, Bands.Length);
                float bandVal = bandIdx < Bands.Length ? Bands[bandIdx] : 0;

                if (bandVal > 0.15 || (ChaosFactor > 0.4 && Random.NextDouble() < ChaosFactor * 0.2))
                {
                    double dotR = ringRadius + bandVal * 25 + (Random.NextDouble() - 0.5) * ChaosFactor * 10;
                    double px = centerX + Math.Cos(angle) * dotR;
                    double py = centerY + Math.Sin(angle) * dotR * 0.5;
                    double dotSize = 2 + bandVal * 7 + _beatFlash * 3;

                    var dotBrush = new RadialGradientBrush
                    {
                        GradientOrigin = new Point(0.5, 0.5),
                        Center = new Point(0.5, 0.5),
                        RadiusX = 0.5,
                        RadiusY = 0.5,
                        GradientStops = new GradientStopCollection
                        {
                            new GradientStop(Colors.White, 0),
                            new GradientStop(Color.FromArgb((byte)(alpha * 255), 150, 220, 255), 0.5),
                            new GradientStop(Color.FromArgb(0, 0, 0, 0), 1)
                        }
                    };
                    dc.DrawEllipse(dotBrush, null, new Point(px, py), dotSize, dotSize * 0.5);
                }
            }
        }
    }
}