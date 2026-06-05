using System;
using System.IO;
using NAudio.Wave;
using NAudio.Wave.SampleProviders;

namespace 音频可视化.Audio;

public class AudioPlayer : IDisposable
{
    private WaveOutEvent? _waveOut;
    private AudioFileReader? _audioFileReader;
    private SampleAggregator? _sampleAggregator;
    private string? _currentFilePath;
    private bool _disposed;

    public event EventHandler? PlaybackStopped;
    public event EventHandler<float[]>? FftCalculated;

    public WaveOutEvent? WaveOut => _waveOut;
    public AudioFileReader? AudioFile => _audioFileReader;
    public SampleAggregator? SampleAgg => _sampleAggregator;

    public TimeSpan CurrentPosition => _audioFileReader?.CurrentTime ?? TimeSpan.Zero;
    public TimeSpan TotalDuration => _audioFileReader?.TotalTime ?? TimeSpan.Zero;

    public bool IsPlaying => _waveOut?.PlaybackState == PlaybackState.Playing;
    public bool IsPaused => _waveOut?.PlaybackState == PlaybackState.Paused;

    public void LoadFile(string filePath)
    {
        Stop();
        DisposeAudio();

        _audioFileReader = new AudioFileReader(filePath);
        _sampleAggregator = new SampleAggregator(_audioFileReader);
        _sampleAggregator.FftCalculated += OnFftCalculated;
        _sampleAggregator.PerformFft = true;

        _waveOut = new WaveOutEvent();
        _waveOut.Init(_sampleAggregator);
        _waveOut.PlaybackStopped += OnPlaybackStopped;

        _currentFilePath = filePath;
    }

    public void Play()
    {
        if (_waveOut == null || _audioFileReader == null) return;
        _waveOut.Play();
    }

    public void Pause()
    {
        _waveOut?.Pause();
    }

    public void Stop()
    {
        if (_waveOut != null)
        {
            _waveOut.Stop();
            if (_audioFileReader != null)
            {
                _audioFileReader.Position = 0;
            }
        }
    }

    public void Seek(TimeSpan position)
    {
        if (_audioFileReader != null)
        {
            _audioFileReader.CurrentTime = position;
        }
    }

    public void SetVolume(double volume)
    {
        if (_waveOut != null)
        {
            _waveOut.Volume = (float)Math.Clamp(volume, 0, 1);
        }
    }

    private void OnFftCalculated(object? sender, float[] fftData)
    {
        FftCalculated?.Invoke(this, fftData);
    }

    private void OnPlaybackStopped(object? sender, StoppedEventArgs e)
    {
        PlaybackStopped?.Invoke(this, EventArgs.Empty);
    }

    private void DisposeAudio()
    {
        if (_sampleAggregator != null)
        {
            _sampleAggregator.FftCalculated -= OnFftCalculated;
            _sampleAggregator = null;
        }

        _waveOut?.Dispose();
        _waveOut = null;

        _audioFileReader?.Dispose();
        _audioFileReader = null;
    }

    public void Dispose()
    {
        if (_disposed) return;
        DisposeAudio();
        _disposed = true;
    }
}

public class SampleAggregator : ISampleProvider
{
    private readonly ISampleProvider _source;
    private readonly int _fftLength;
    private readonly Complex[] _fftBuffer;
    private readonly float[] _fftResult;
    private readonly float[] _windowBuffer;
    private int _fftPos;

    public event EventHandler<float[]>? FftCalculated;
    public bool PerformFft { get; set; }

    public WaveFormat WaveFormat => _source.WaveFormat;

    public SampleAggregator(ISampleProvider source, int fftLength = 2048)
    {
        _source = source;
        _fftLength = fftLength;
        _fftBuffer = new Complex[fftLength];
        _fftResult = new float[fftLength / 2];
        _windowBuffer = new float[fftLength];

        for (int i = 0; i < fftLength; i++)
        {
            _windowBuffer[i] = (float)(0.5 - 0.5 * Math.Cos(2.0 * Math.PI * i / (fftLength - 1)));
        }
    }

    public int Read(float[] buffer, int offset, int count)
    {
        int samplesRead = _source.Read(buffer, offset, count);

        if (PerformFft)
        {
            for (int i = 0; i < samplesRead; i++)
            {
                _fftBuffer[_fftPos].X = buffer[offset + i] * _windowBuffer[_fftPos];
                _fftBuffer[_fftPos].Y = 0;
                _fftPos++;

                if (_fftPos >= _fftLength)
                {
                    _fftPos = 0;
                    var fftCopy = new Complex[_fftLength];
                    Array.Copy(_fftBuffer, fftCopy, _fftLength);
                    FastFourierTransform.FFT(true, (int)Math.Log2(_fftLength), fftCopy);

                    for (int j = 0; j < _fftLength / 2; j++)
                    {
                        float magnitude = (float)Math.Sqrt(
                            fftCopy[j].X * fftCopy[j].X +
                            fftCopy[j].Y * fftCopy[j].Y);
                        _fftResult[j] = magnitude * 2.0f / _fftLength;
                    }

                    FftCalculated?.Invoke(this, _fftResult);
                }
            }
        }

        return samplesRead;
    }
}

public struct Complex
{
    public float X { get; set; }
    public float Y { get; set; }
}

public static class FastFourierTransform
{
    public static void FFT(bool forward, int m, Complex[] data)
    {
        int n = 1 << m;
        float angle = forward ? -2.0f * (float)Math.PI / n : 2.0f * (float)Math.PI / n;

        for (int i = 0; i < n; i++)
        {
            int j = 0;
            for (int bit = 0; bit < m; bit++)
            {
                j = (j << 1) | ((i >> bit) & 1);
            }
            if (j > i)
            {
                (data[i], data[j]) = (data[j], data[i]);
            }
        }

        for (int len = 2; len <= n; len <<= 1)
        {
            float halfAngle = angle * (n / len);
            for (int i = 0; i < n; i += len)
            {
                float wReal = 1;
                float wImag = 0;
                for (int j = 0; j < len / 2; j++)
                {
                    float tReal = wReal * data[i + j + len / 2].X - wImag * data[i + j + len / 2].Y;
                    float tImag = wReal * data[i + j + len / 2].Y + wImag * data[i + j + len / 2].X;

                    data[i + j + len / 2].X = data[i + j].X - tReal;
                    data[i + j + len / 2].Y = data[i + j].Y - tImag;
                    data[i + j].X += tReal;
                    data[i + j].Y += tImag;

                    float newWReal = wReal * halfAngle - wImag * halfAngle;
                    wImag = wReal * halfAngle + wImag * halfAngle;
                    wReal = newWReal;
                }
            }
        }
    }
}
