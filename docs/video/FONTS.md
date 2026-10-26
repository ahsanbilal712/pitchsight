# Fonts in the video

## v9 on: Inter

Every on-screen word of the PITCHSIGHT video from v9 (overlays, cards, captions) is set in **Inter** (Regular, SemiBold,
Bold), version 4.1, by Rasmus Andersson and the Inter Project Authors.

- Source: the official release, https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip, downloaded
  26 Oct 2026. The TTFs and `LICENSE.txt` are extracted to `packages/demo/out/fonts/`
  (git-ignored); no font file is committed.
- Licence: SIL Open Font License 1.1 (https://openfontlicense.org). Free to use, embed in a video, bundle and
  redistribute; the font itself may not be sold on its own, and modified versions must not use the reserved name.
- The renderers (`demo.live`, `demo.composite`, `demo.assemble`) use Inter when those files are present and fall
  back to DejaVu Sans otherwise.

## v8: DejaVu Sans

The v8 video is set in **DejaVu Sans** (Bold and Book), read from the copy matplotlib ships
(`matplotlib/mpl-data/fonts/ttf/DejaVuSans*.ttf`). DejaVu derives from Bitstream Vera: the Vera glyphs are under the
Bitstream Vera Fonts licence (free to use, copy, modify, embed and redistribute, including commercially; not to be
sold on its own; modified versions renamed), and DejaVu's changes are in the public domain.
Full text: https://dejavu-fonts.github.io/License.html (also in matplotlib's LICENSE_DEJAVU).
