using System.Windows;
using System.Windows.Media;

namespace 音频可视化;

public class DrawingCanvas : FrameworkElement
{
    private readonly DrawingVisual _visual = new();

    public DrawingCanvas()
    {
        AddVisualChild(_visual);
    }

    public DrawingGroup DrawingGroup { get; set; } = new();

    protected override int VisualChildrenCount => 1;

    protected override Visual GetVisualChild(int index)
    {
        return _visual;
    }

    protected override void OnRender(DrawingContext drawingContext)
    {
        drawingContext.DrawDrawing(DrawingGroup);
    }
}