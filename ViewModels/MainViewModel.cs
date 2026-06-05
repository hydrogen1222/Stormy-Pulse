using System;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Windows.Threading;
using 音频可视化.Audio;
using 音频可视化.Visualization;
using Microsoft.Win32;

namespace 音频可视化.ViewModels;

public enum VisualizationMode
{
    Bar,
    Circular,
    Particle
}

public class MainViewModel : INotifyPropertyChanged, IDisposable
{
    private readonly AudioPlayer _audioPlayer;
    private readonly AudioAnalyzer _audioAnalyzer;
    private readonly DispatcherTimer _uiTimer;

    private BaseVisualization _currentVisualization;
    private VisualizationMode _visualizationMode = VisualizationMode.Bar;
    private bool _isPlaying;
    private string? _currentFileName;
    private TimeSpan _currentPosition;
    private TimeSpan _totalDuration;
    private double _positionPercent;
    private bool _isFileLoaded;
    private double _volume = 0.8;

    public event PropertyChangedEventHandler? PropertyChanged;

    public BaseVisualization CurrentVisualization => _currentVisualization;

    public VisualizationMode VisualizationMode
    {
        get => _visualizationMode;
        set
        {
            if (_visualizationMode != value)
            {
                _visualizationMode = value;
                OnPropertyChanged();
                SwitchVisualization();
            }
        }
    }

    public bool IsPlaying
    {
        get => _isPlaying;
        private set { _isPlaying = value; OnPropertyChanged(); OnPropertyChanged(nameof(PlayPauseIcon)); }
    }

    public string? CurrentFileName
    {
        get => _currentFileName;
        private set { _currentFileName = value; OnPropertyChanged(); }
    }

    public TimeSpan CurrentPosition
    {
        get => _currentPosition;
        private set { _currentPosition = value; OnPropertyChanged(); OnPropertyChanged(nameof(PositionText)); }
    }

    public TimeSpan TotalDuration
    {
        get => _totalDuration;
        private set { _totalDuration = value; OnPropertyChanged(); OnPropertyChanged(nameof(PositionText)); }
    }

    public double PositionPercent
    {
        get => _positionPercent;
        set
        {
            if (Math.Abs(_positionPercent - value) > 0.1)
            {
                _positionPercent = value;
                OnPropertyChanged();
                if (_isFileLoaded && TotalDuration.TotalSeconds > 0)
                {
                    var newPos = TimeSpan.FromSeconds(TotalDuration.TotalSeconds * value / 100);
                    _audioPlayer.Seek(newPos);
                }
            }
        }
    }

    public double Volume
    {
        get => _volume;
        set
        {
            _volume = Math.Clamp(value, 0, 1);
            OnPropertyChanged();
            _audioPlayer.SetVolume(_volume);
        }
    }

    public string PositionText => $"{CurrentPosition:mm\\:ss} / {TotalDuration:mm\\:ss}";

    public string PlayPauseIcon => IsPlaying ? "\uE769" : "\uE768";

    public bool IsFileLoaded
    {
        get => _isFileLoaded;
        private set { _isFileLoaded = value; OnPropertyChanged(); }
    }

    public MainViewModel()
    {
        _audioPlayer = new AudioPlayer();
        _audioAnalyzer = new AudioAnalyzer();
        _currentVisualization = new BarVisualization();

        _audioPlayer.FftCalculated += OnFftCalculated;
        _audioPlayer.PlaybackStopped += OnPlaybackStopped;
        _audioPlayer.SetVolume(_volume);

        _uiTimer = new DispatcherTimer
        {
            Interval = TimeSpan.FromMilliseconds(100)
        };
        _uiTimer.Tick += OnUiTimerTick;
    }

    public void OpenFile()
    {
        var dialog = new OpenFileDialog
        {
            Filter = "音频文件|*.mp3;*.wav;*.flac;*.m4a;*.ogg|所有文件|*.*",
            Title = "打开音频文件"
        };

        if (dialog.ShowDialog() == true)
        {
            LoadFile(dialog.FileName);
        }
    }

    public void LoadFile(string filePath)
    {
        try
        {
            _audioPlayer.LoadFile(filePath);
            _audioAnalyzer.Reset();

            CurrentFileName = System.IO.Path.GetFileName(filePath);
            TotalDuration = _audioPlayer.TotalDuration;
            CurrentPosition = TimeSpan.Zero;
            PositionPercent = 0;
            IsFileLoaded = true;

            _uiTimer.Start();
        }
        catch (Exception ex)
        {
            System.Windows.MessageBox.Show($"无法加载文件: {ex.Message}", "错误");
        }
    }

    public void PlayPause()
    {
        if (!IsFileLoaded) return;

        if (IsPlaying)
        {
            _audioPlayer.Pause();
            IsPlaying = false;
        }
        else
        {
            _audioPlayer.Play();
            IsPlaying = true;
        }
    }

    public void Stop()
    {
        if (!IsFileLoaded) return;

        _audioPlayer.Stop();
        IsPlaying = false;
        CurrentPosition = TimeSpan.Zero;
        PositionPercent = 0;
    }

    private void OnFftCalculated(object? sender, float[] fftData)
    {
        _audioAnalyzer.ProcessFftData(fftData);

        // Update visualization data with rhythm features for chaotic effects
        _currentVisualization.UpdateData(
            _audioAnalyzer.Bands,
            _audioAnalyzer.BassLevel,
            _audioAnalyzer.MidLevel,
            _audioAnalyzer.HighLevel,
            _audioAnalyzer.OverallLevel
        );

        _currentVisualization.UpdateRhythmData(
            _audioAnalyzer.SpectralFlux,
            _audioAnalyzer.TransientStrength,
            _audioAnalyzer.BeatPulse,
            _audioAnalyzer.ChaosFactor
        );

        _currentVisualization.UpdateBeatData(
            _audioAnalyzer.OnBeat,
            _audioAnalyzer.BeatStrength,
            _audioAnalyzer.EstimatedBpm,
            _audioAnalyzer.BeatPhase,
            _audioAnalyzer.SpectralCentroid,
            _audioAnalyzer.SpectralRolloff
        );
    }

    private void OnPlaybackStopped(object? sender, EventArgs e)
    {
        System.Windows.Application.Current?.Dispatcher.Invoke(() =>
        {
            IsPlaying = false;
            if (TotalDuration > TimeSpan.Zero && CurrentPosition >= TotalDuration - TimeSpan.FromSeconds(1))
            {
                Stop();
            }
        });
    }

    private void OnUiTimerTick(object? sender, EventArgs e)
    {
        if (IsFileLoaded && !IsPlaying)
        {
            CurrentPosition = _audioPlayer.CurrentPosition;
            if (TotalDuration.TotalSeconds > 0)
            {
                PositionPercent = (CurrentPosition.TotalSeconds / TotalDuration.TotalSeconds) * 100;
            }
        }
    }

    private void SwitchVisualization()
    {
        _currentVisualization = _visualizationMode switch
        {
            VisualizationMode.Bar => new BarVisualization(),
            VisualizationMode.Circular => new CircularVisualization(),
            VisualizationMode.Particle => new ParticleVisualization(),
            _ => _currentVisualization
        };
        OnPropertyChanged(nameof(CurrentVisualization));
    }

    protected virtual void OnPropertyChanged([CallerMemberName] string? propertyName = null)
    {
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
    }

    public void Dispose()
    {
        _uiTimer.Stop();
        _audioPlayer.FftCalculated -= OnFftCalculated;
        _audioPlayer.PlaybackStopped -= OnPlaybackStopped;
        _audioPlayer.Dispose();
    }
}
