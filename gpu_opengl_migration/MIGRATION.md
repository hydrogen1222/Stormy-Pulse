# GPU Migration Notes

This directory is an isolated copy of the current player codebase used for the
OpenGL migration experiment. The original source tree in the repository root is
left untouched.

Current migration approach:

1. Keep the existing scene/update/theme logic.
2. Split rendering into two layers:
   - `OpenGLSceneWidget`: heavy scene layers inside a `QOpenGLWidget`
   - `HudOverlayRenderer`: transparent HUD/title/lyrics overlay
3. Keep export and playback logic functional while preparing the heavy layers
   for a later shader rewrite.

This stage focuses on architecture separation, not on a complete shader-based
replacement yet.
