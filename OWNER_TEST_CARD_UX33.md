# UX33 owner acceptance · Zorin Linux Xorg

1. Confirm version `0.7.17-ux33`. Open the **Transition** rack from the top performance toolbar. There should be no wipe/pixel/glitch preset arrows and no duplicate shape/ease/edge selector. The edit target should still show A/B TRANSITION.
2. Open **Modules**. The library should have Single/Groups/Saved plus direct family categories. Motion should show Reveal Field, Timing Curve, Iris Field, Pixel Field, Tear Field, Slide Motion and editable named groups.
3. Add **Directional Wipe**, change timing start/end/curve and Reveal angle/softness, and crossfade A→B while watching an animated visual source. Observe intermediate motion and unchanged A/B endpoints.
4. Switch to **Pixel Scatter** or **Glitch Tear**. Edit cell size, randomness, band count, displacement, or noise; compare the actual rendered animation as you crossfade. The effect must not behave as an uneditable preset.
5. Add **Iris Bloom** and **Moving Slide**. Edit centre, direction and travel. Group/ungroup, reorder, bypass, undo/redo. Save and reload an instrument, verify the same animation parameters and grouped effects survive.
6. Under the Transition family choose **↧ Import**, and open `examples/recipes/Custom_Pixel_Gate.neospector-module.json`. Find **Custom Pixel Gate** in Saved, add it, and edit its promoted parameters. The parser should reject unknown or out-of-range effects; it never executes user-provided code.
7. Switch to the normal A/B or Output rack. Transition geometry should be absent from its library; normal colour/texture/spatial modules and ordinary groups remain available.
8. Check queues and camera switching, music and microphone reaction, source import, recording and export. No old settings or live sources should be silently replaced. Resize the window with the Modules Library open to check wrap/scroll/legibility.

**Qualification:** Automated verification can validate model/Tk logic and package integrity, but not perceptual smoothness with real moving video, hardware audio capture, recording/export success or user acceptance. Preserve UX32 as rollback until confirmed.
