using System;

namespace 音频可视化.Audio;

public class AudioAnalyzer
{
    public const int BandCount = 64;
    private readonly float[] _smoothedBands;
    private readonly float[] _previousBands;
    private readonly float[] _spectralFlux;
    private readonly float[] _energyHistory;
    private readonly float[] _onsetHistory;
    private int _historyIndex;
    private readonly int _historySize = 43;

    private readonly float _smoothingFactor = 0.25f;
    private readonly float _decayFactor = 0.88f;

    // Beat detection
    private float _energySum;
    private float _onsetSum;
    private float _beatThreshold;
    private float _lastBeatEnergy;
    private float _beatDecay;
    private int _samplesSinceLastBeat;
    private float _beatInterval;
    private float _estimatedBpm;
    private float _beatStrength;
    private float _onBeat;
    private float _beatPhase;

    // Rhythm and chaos features
    private float _spectralFluxSum;
    private float _transientStrength;
    private float _beatPulse;
    private float _chaosFactor;
    private float _previousBass;
    private float _previousMid;
    private float _previousHigh;
    private float _attackStrength;

    // Energy tracking
    private float _peakEnergy;
    private float _energyVariance;

    // Spectral features
    private float _spectralCentroid;
    private float _spectralRolloff;

    public float[] Bands => _smoothedBands;

    public float BassLevel { get; private set; }
    public float MidLevel { get; private set; }
    public float HighLevel { get; private set; }
    public float OverallLevel { get; private set; }

    // Beat detection features
    public float SpectralFlux => _spectralFluxSum;
    public float TransientStrength => _transientStrength;
    public float BeatPulse => _beatPulse;
    public float ChaosFactor => _chaosFactor;
    public float AttackStrength => _attackStrength;
    public float EnergyVariance => _energyVariance;
    public float PeakEnergy => _peakEnergy;

    public float OnBeat => _onBeat;
    public float BeatStrength => _beatStrength;
    public float EstimatedBpm => _estimatedBpm;
    public float BeatPhase => _beatPhase;
    public float SpectralCentroid => _spectralCentroid;
    public float SpectralRolloff => _spectralRolloff;

    public AudioAnalyzer()
    {
        _smoothedBands = new float[BandCount];
        _previousBands = new float[BandCount];
        _spectralFlux = new float[BandCount];
        _energyHistory = new float[_historySize];
        _onsetHistory = new float[_historySize];
    }

    public void ProcessFftData(float[] fftData)
    {
        if (fftData == null || fftData.Length == 0) return;

        int bandsPerGroup = Math.Max(1, fftData.Length / BandCount);
        float total = 0;
        const float minDb = -90f;
        const float maxDb = 0f;

        float flux = 0;
        float maxBandChange = 0;
        float centroidSum = 0;
        float centroidWeight = 0;
        float totalMagnitude = 0;

        for (int i = 0; i < BandCount; i++)
        {
            float sum = 0;
            int startIdx = i * bandsPerGroup;
            for (int j = 0; j < bandsPerGroup; j++)
            {
                int idx = startIdx + j;
                if (idx < fftData.Length)
                {
                    sum += fftData[idx];
                    float freq = idx * 44100f / fftData.Length / 2;
                    centroidSum += freq * fftData[idx];
                    centroidWeight += fftData[idx];
                    totalMagnitude += fftData[idx];
                }
            }

            float rawValue = sum / bandsPerGroup;

            float dbValue;
            if (rawValue > 0.000001f)
            {
                dbValue = (float)(20 * Math.Log10(rawValue));
                dbValue = Math.Clamp((dbValue - minDb) / (maxDb - minDb), 0, 1);
            }
            else
            {
                dbValue = 0;
            }

            float change = dbValue - _previousBands[i];
            if (change > 0)
            {
                flux += change;
                maxBandChange = Math.Max(maxBandChange, change);
            }
            _spectralFlux[i] = change > 0 ? change : 0;

            _previousBands[i] = _smoothedBands[i];

            if (dbValue > _smoothedBands[i])
            {
                _smoothedBands[i] = dbValue * _smoothingFactor + _smoothedBands[i] * (1 - _smoothingFactor);
                _attackStrength = Math.Min(_attackStrength + 0.15f, 1f);
            }
            else
            {
                _smoothedBands[i] *= _decayFactor;
                _attackStrength *= 0.92f;
            }

            total += _smoothedBands[i];
        }

        _spectralFluxSum = Math.Min(flux / BandCount * 12, 1f);

        if (centroidWeight > 0)
            _spectralCentroid = centroidSum / centroidWeight / 1000f;

        float rolloffThreshold = totalMagnitude * 0.85f;
        float cumsum = 0;
        for (int i = 0; i < fftData.Length && i < BandCount * bandsPerGroup; i++)
        {
            cumsum += fftData[i * bandsPerGroup / Math.Max(1, BandCount)];
            if (cumsum >= rolloffThreshold)
            {
                _spectralRolloff = i * bandsPerGroup * 44100f / fftData.Length / 2000f;
                break;
            }
        }

        float bassChange = Math.Abs(BassLevel - _previousBass);
        float midChange = Math.Abs(MidLevel - _previousMid);
        float highChange = Math.Abs(HighLevel - _previousHigh);
        float totalChange = bassChange + midChange + highChange;

        _previousBass = BassLevel;
        _previousMid = MidLevel;
        _previousHigh = HighLevel;

        _transientStrength += (totalChange * 6f - _transientStrength) * 0.35f;
        _transientStrength = Math.Max(_transientStrength * 0.94f, 0);

        OverallLevel = total / BandCount;

        _peakEnergy = Math.Max(_peakEnergy * 0.985f, OverallLevel);
        float instantVariance = Math.Abs(_peakEnergy - OverallLevel);
        _energyVariance += (instantVariance - _energyVariance) * 0.12f;

        int bassEnd = BandCount / 8;
        int midEnd = BandCount / 2;

        float bassSum = 0;
        for (int i = 0; i < bassEnd; i++)
            bassSum += _smoothedBands[i];
        BassLevel = bassSum / bassEnd;

        float midSum = 0;
        for (int i = bassEnd; i < midEnd; i++)
            midSum += _smoothedBands[i];
        MidLevel = midSum / (midEnd - bassEnd);

        float highSum = 0;
        for (int i = midEnd; i < BandCount; i++)
            highSum += _smoothedBands[i];
        HighLevel = highSum / (BandCount - midEnd);

        float bassEnergy = BassLevel;
        float totalEnergy = OverallLevel;

        _historyIndex = (_historyIndex + 1) % _historySize;
        _energyHistory[_historyIndex] = totalEnergy;
        _onsetHistory[_historyIndex] = _spectralFluxSum;

        _energySum = 0;
        _onsetSum = 0;
        for (int i = 0; i < _historySize; i++)
        {
            _energySum += _energyHistory[i];
            _onsetSum += _onsetHistory[i];
        }
        float avgEnergy = _energySum / _historySize;
        float avgOnset = _onsetSum / _historySize;

        _beatThreshold = avgEnergy * 1.4f + avgOnset * 0.8f + 0.05f;
        _beatThreshold = Math.Min(_beatThreshold, 0.85f);

        bool isBeat = totalEnergy > _beatThreshold &&
                      totalEnergy > _lastBeatEnergy * 1.1f &&
                      _spectralFluxSum > avgOnset * 1.5f;

        if (isBeat && _samplesSinceLastBeat > 15)
        {
            float timeSinceLastBeat = _samplesSinceLastBeat / 60f;
            _beatStrength = Math.Min(totalEnergy * 1.5f + _spectralFluxSum * 0.8f, 1.5f);

            if (timeSinceLastBeat > 0.2f && timeSinceLastBeat < 2.0f)
            {
                float predictedInterval = timeSinceLastBeat;
                _beatInterval = _beatInterval * 0.7f + predictedInterval * 0.3f;

                if (_beatInterval > 0.3f)
                    _estimatedBpm = 60f / _beatInterval;
                _estimatedBpm = Math.Clamp(_estimatedBpm, 60f, 180f);
            }

            _lastBeatEnergy = totalEnergy;
            _beatDecay = 0.18f;
            _samplesSinceLastBeat = 0;
        }
        else
        {
            _beatDecay *= 0.95f;
            _lastBeatEnergy *= 0.97f;
        }

        _samplesSinceLastBeat++;

        _onBeat = _beatDecay;
        _beatDecay = Math.Max(_beatDecay - 0.012f, 0);

        _beatPulse = _beatPulse * 0.85f + _beatStrength * 0.15f;
        _beatStrength *= 0.92f;

        if (_estimatedBpm > 0)
        {
            _beatPhase += _estimatedBpm / 60f * 0.016f;
            if (_beatPhase > 1f) _beatPhase -= 1f;
        }

        float chaosComponents =
            _spectralFluxSum * 0.35f +
            _transientStrength * 0.25f +
            _beatPulse * 0.25f +
            _energyVariance * 0.15f;

        float randomChaos = (float)(new Random().NextDouble() * 0.08);
        _chaosFactor += (chaosComponents + randomChaos - _chaosFactor) * 0.18f;
        _chaosFactor = Math.Clamp(_chaosFactor, 0, 1);
    }

    public void Reset()
    {
        Array.Clear(_smoothedBands, 0, _smoothedBands.Length);
        Array.Clear(_previousBands, 0, _previousBands.Length);
        Array.Clear(_spectralFlux, 0, _spectralFlux.Length);
        Array.Clear(_energyHistory, 0, _energyHistory.Length);
        Array.Clear(_onsetHistory, 0, _onsetHistory.Length);

        BassLevel = 0;
        MidLevel = 0;
        HighLevel = 0;
        OverallLevel = 0;
        _spectralFluxSum = 0;
        _transientStrength = 0;
        _beatPulse = 0;
        _chaosFactor = 0;
        _attackStrength = 0;
        _energyVariance = 0;
        _peakEnergy = 0;
        _previousBass = 0;
        _previousMid = 0;
        _previousHigh = 0;

        _estimatedBpm = 120f;
        _beatStrength = 0;
        _onBeat = 0;
        _beatDecay = 0;
        _beatInterval = 0.5f;
        _samplesSinceLastBeat = 100;
        _lastBeatEnergy = 0;
        _beatThreshold = 0.2f;
        _historyIndex = 0;

        _spectralCentroid = 0;
        _spectralRolloff = 0;
    }
}
