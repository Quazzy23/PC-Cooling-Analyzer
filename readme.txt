================================================================================
                            ANALYZER — USER GUIDE
================================================================================

This guide covers the interface layout, mouse controls, hotkeys, and features
of the 'analyzer.py' workstation.

================================================================================
 1. GLOBAL INTERFACE & LAYOUT
================================================================================
• MODULES TOGGLES (Top Bar): 
  - [Telemetry]: Displays the Sidebar and Hardware Dynamics charts (P1/P2).
  - [Audio DAW]: Displays the Live FFT and 2D Spectrogram Timeline.
  - You can view them together or isolate one module in full-screen.
  
• RESIZABLE PANELS: 
  - All vertical splitter lines between panels can be dragged left/right.
  - Horizontal lines between P1/P2 and FFT/Spectrogram can be dragged up/down.
  - The border between Summary Metrics and Sensor Passport is also adjustable.

================================================================================
 2. SENSOR PASSPORT (LEFT SIDEBAR)
================================================================================
This area controls what is displayed on the P1 and P2 hardware charts.

• CHECKBOX [■] : Shows or hides the sensor curve on the chart.
• [L]/[R] BTN  : Assigns the sensor to the Left or Right Y-axis scale.
• [B] BUTTON   : Locks/Unlocks the sensor's Y-axis for manual zooming (see below).
• DRAG & DROP  : 
  - Click and drag the grip icon [⠿] UP or DOWN to change the Z-layer of the 
    curve (higher in the list = on top of other curves).
  - Drag a sensor from Panel 1 into Panel 2 to instantly move it to the bottom chart.
• SAVE PRESET  : Click "Save View Preset" to permanently save your layers, colors, 
  and visibility state for the active profile.

================================================================================
 3. MOUSE CONTROLS & HOTKEYS
================================================================================
• LEFT CLICK (LMB) : Places the global timeline cursor across all charts. 
  It updates the live values and instantly seeks the audio playback to that time.
  
• MIDDLE CLICK & DRAG (Scroll Wheel Click) : Pan / Move the chart around.

• ALT   + SCROLL WHEEL : Zoom In/Out along the X-axis (Time / Frequency).
• SHIFT + SCROLL WHEEL : Zoom In/Out along the Y-axis (Value / Amplitude).
  * Note for Telemetry: Y-axis zoom only works for sensors with the [M] button enabled.

• RIGHT CLICK (RMB) — REGION SELECTION:
  - Drag RMB: Draws a highlighted region on the chart.
    > On Telemetry: Recalculates Min/Max/Avg in the Summary Metrics table.
    > On Audio DAW: Isolates and filters the specific frequency/time band.
  - CTRL + Drag RMB: Adds multiple independent regions simultaneously.
  - Single RMB click inside a region: Deletes that specific region.
  - Single RMB click on empty space: Clears ALL selected regions.

• KEYBOARD HOTKEYS:
  - SPACEBAR : Play / Pause audio playback and timeline tracking.
  - ESCAPE   : Clear all selected regions and filters.

================================================================================
 4. BOTTOM TOOLBAR CONTROLS
================================================================================
TELEMETRY CONTROLS:
• Smooth  : Applies a rolling mean window to the raw curve (e.g. 4 = smooth).
• Step    : Downsamples the trend line (e.g. 10 = plots every 10th data point).
• Raw Fog : Opacity (Alpha) of the raw background curve (0.0 to 1.0).
• Trend A : Opacity (Alpha) of the smoothed trend line (0.0 to 1.0).
• Fit     : Toggles auto-scaling logic between Raw data bounds and Trend bounds.
• Save    : Exports the current timeline constraints into a new trend-based CSV.

AUDIO DAW CONTROLS:
• Play    : Starts or pauses the audio stream (Shortcut: Spacebar).
• Boost   : Applies digital gain (in dB) to the audio playback.
• Render  : Renders a high-resolution Spectrogram for the currently zoomed-in area.
• Scale   : Toggles the FFT Frequency X-axis between Logarithmic and Linear views.
• Y Min/Max: Manually sets the bottom and top dB limits for the Live FFT chart.

================================================================================
 5. SUMMARY METRICS TABLE
================================================================================
• Automatically calculates the Minimum, Maximum, and Average values.
• If no regions are selected (RMB), it calculates stats for the entire log.
• If you draw one or multiple time regions with RMB, the table instantly recalculates 
  stats ONLY for the selected timeframes.