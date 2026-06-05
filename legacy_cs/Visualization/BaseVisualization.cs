using System;
using System.Windows;
using System.Windows.Media;

namespace 音频可视化.Visualization;

public abstract class BaseVisualization
{
    protected float[] Bands = Array.Empty<float>();
    protected float BassLevel;
    protected float MidLevel;
    protected float HighLevel;
    protected float OverallLevel;

    // New rhythm-aware features
    protected float SpectralFlux;
    protected float TransientStrength;
    protected float BeatPulse;
    protected float ChaosFactor;
    protected float OnBeat;
    protected float BeatStrength;
    protected float EstimatedBpm = 120f;
    protected float BeatPhase;
    protected float SpectralCentroid;
    protected float SpectralRolloff;

    protected Random Random = new();

    public abstract void Render(DrawingContext dc, Rect bounds);

    public virtual void UpdateData(float[] bands, float bass, float mid, float high, float overall)
    {
        Bands = bands;
        BassLevel = bass;
        MidLevel = mid;
        HighLevel = high;
        OverallLevel = overall;
    }

    public virtual void UpdateRhythmData(float spectralFlux, float transient, float beat, float chaos)
    {
        SpectralFlux = spectralFlux;
        TransientStrength = transient;
        BeatPulse = beat;
        ChaosFactor = chaos;
    }

    public virtual void UpdateBeatData(float onBeat, float beatStrength, float bpm, float beatPhase, float centroid, float rolloff)
    {
        OnBeat = onBeat;
        BeatStrength = beatStrength;
        EstimatedBpm = bpm > 0 ? bpm : 120f;
        BeatPhase = beatPhase;
        SpectralCentroid = centroid;
        SpectralRolloff = rolloff;
    }

    protected Color HsvToColor(double h, double s, double v, double alpha = 1.0)
    {
        int hi = (int)(h / 60.0) % 6;
        double f = h / 60.0 - Math.Floor(h / 60.0);

        byte r, g, b;
        switch (hi)
        {
            case 0:
                r = (byte)(255 * Math.Clamp(v, 0, 1)); g = (byte)(255 * Math.Clamp(v * (1 - s * (1 - f)), 0, 1)); b = (byte)(255 * Math.Clamp(v * (1 - s), 0, 1));
                break;
            case 1:
                r = (byte)(255 * Math.Clamp(v * (1 - s * f), 0, 1)); g = (byte)(255 * Math.Clamp(v, 0, 1)); b = (byte)(255 * Math.Clamp(v * (1 - s), 0, 1));
                break;
            case 2:
                r = (byte)(255 * Math.Clamp(v * (1 - s), 0, 1)); g = (byte)(255 * Math.Clamp(v, 0, 1)); b = (byte)(255 * Math.Clamp(v * (1 - s * (1 - f)), 0, 1));
                break;
            case 3:
                r = (byte)(255 * Math.Clamp(v * (1 - s), 0, 1)); g = (byte)(255 * Math.Clamp(v * (1 - s * f), 0, 1)); b = (byte)(255 * Math.Clamp(v, 0, 1));
                break;
            case 4:
                r = (byte)(255 * Math.Clamp(v * (1 - s * (1 - f)), 0, 1)); g = (byte)(255 * Math.Clamp(v * (1 - s), 0, 1)); b = (byte)(255 * Math.Clamp(v, 0, 1));
                break;
            default:
                r = (byte)(255 * Math.Clamp(v, 0, 1)); g = (byte)(255 * Math.Clamp(v * (1 - s), 0, 1)); b = (byte)(255 * Math.Clamp(v * (1 - s * f), 0, 1));
                break;
        }
        return Color.FromArgb((byte)(alpha * 255), r, g, b);
    }

    protected void DrawGlow(DrawingContext dc, Geometry geometry, Color color, double blurRadius)
    {
        var glowBrush = new RadialGradientBrush
        {
            GradientOrigin = new Point(0.5, 0.5),
            Center = new Point(0.5, 0.5),
            RadiusX = 0.5,
            RadiusY = 0.5,
            GradientStops = new GradientStopCollection
            {
                new(color, 0),
                new(Color.FromArgb(0, color.R, color.G, color.B), 1)
            }
        };

        dc.DrawGeometry(glowBrush, null, geometry);
    }

    protected double Jitter(double baseValue, double range)
    {
        return baseValue + (Random.NextDouble() - 0.5) * range * ChaosFactor;
    }
}
