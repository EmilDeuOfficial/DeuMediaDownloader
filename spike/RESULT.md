# Frameless window spike result

Verdict: viable. pywebview 6.2.1 on Windows 11 (WebView2), Python 3.12.

- Drag: the `pywebview-drag-region` class is picked up (`easy_drag=False`).
- Resize: a frameless window has no native edge resize. Eight fixed-position edge
  handles in the DOM plus `window.resize(w, h, fix_point)` from Python work for all
  edges and corners, including the west/north edges (fix point EAST/SOUTH keeps the
  opposite edge in place). Verified by synthetic pointer events: 820x720 at (200,150)
  became 940x820 at (160,120) after e+60, w-40, s+50, n-30, se+20/20.
- min_size: `resize()` is clamped to the native `min_size`. A 720x360 launcher cannot
  be set while `min_size=(700, 600)`. Decision: create the window with a small native
  minimum and enforce the per-view minimum in `Api.set_view` and in the JS handles.
- Initial size: a window created with 820x720 reports 804x681 (frame removed after
  the size was applied). Call `resize()` once after the window is shown.
- Maximize: covers the full screen (1920x1080), same as the old Tk app which used
  `screenwidth x screenheight`.
- `resize/move/maximize/minimize/restore/evaluate_js` are safe to call from worker
  threads.
