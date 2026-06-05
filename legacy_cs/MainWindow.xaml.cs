using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using 音频可视化.ViewModels;
using 音频可视化.Visualization;

namespace 音频可视化;

public partial class MainWindow : Window
{
    private readonly MainViewModel _viewModel;
    private bool _isRendering;
    private readonly DrawingGroup _drawingGroup = new();

    public MainWindow()
    {
        InitializeComponent();

        _viewModel = new MainViewModel();
        DataContext = _viewModel;

        VisualizationCanvas.DrawingGroup = _drawingGroup;

        CompositionTarget.Rendering += OnRendering;
        _isRendering = true;

        SizeChanged += OnSizeChanged;
    }

    private void OnSizeChanged(object sender, SizeChangedEventArgs e)
    {
        VisualizationCanvas.Width = Math.Max(e.NewSize.Width - 32, 800);
        VisualizationCanvas.Height = Math.Max(e.NewSize.Height - 140, 400);
    }

    private void OnRendering(object? sender, EventArgs e)
    {
        if (!_isRendering) return;

        var visualization = _viewModel.CurrentVisualization;
        if (visualization == null) return;

        double width = VisualizationCanvas.ActualWidth > 0 ? VisualizationCanvas.ActualWidth : 800;
        double height = VisualizationCanvas.ActualHeight > 0 ? VisualizationCanvas.ActualHeight : 400;

        var dc = _drawingGroup.Open();
        dc.DrawRectangle(new SolidColorBrush(Color.FromRgb(15, 15, 26)), null, new Rect(0, 0, width, height));
        visualization.Render(dc, new Rect(0, 0, width, height));
        dc.Close();

        PositionText.Text = _viewModel.PositionText;
    }

    private void OpenFile_Click(object sender, RoutedEventArgs e)
    {
        _viewModel.OpenFile();
        UpdateUI();
    }

    private void PlayPause_Click(object sender, RoutedEventArgs e)
    {
        _viewModel.PlayPause();
        UpdatePlayPauseButton();
    }

    private void Stop_Click(object sender, RoutedEventArgs e)
    {
        _viewModel.Stop();
        UpdatePlayPauseButton();
    }

    private void PositionSlider_ValueChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (_viewModel != null && PositionSlider.IsEnabled)
        {
            _viewModel.PositionPercent = e.NewValue;
        }
    }

    private void VisualizationMode_Changed(object sender, RoutedEventArgs e)
    {
        if (_viewModel == null) return;

        if (BarMode.IsChecked == true)
        {
            _viewModel.VisualizationMode = VisualizationMode.Bar;
        }
        else if (CircularMode.IsChecked == true)
        {
            _viewModel.VisualizationMode = VisualizationMode.Circular;
        }
        else if (ParticleMode.IsChecked == true)
        {
            _viewModel.VisualizationMode = VisualizationMode.Particle;
        }
    }

    private void VolumeSlider_ValueChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (_viewModel != null)
        {
            _viewModel.Volume = e.NewValue / 100.0;
        }
    }

    private void UpdateUI()
    {
        FileNameText.Text = _viewModel.CurrentFileName ?? "未加载文件";
        UpdatePlayPauseButton();
        VolumeSlider.Value = _viewModel.Volume * 100;
    }

    private void UpdatePlayPauseButton()
    {
        PlayPauseIcon.Text = _viewModel.IsPlaying ? "\uE769" : "\uE768";
    }

    protected override void OnClosed(EventArgs e)
    {
        _isRendering = false;
        CompositionTarget.Rendering -= OnRendering;
        _viewModel.Dispose();
        base.OnClosed(e);
    }
}
