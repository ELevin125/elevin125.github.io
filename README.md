# Emil Levin — Personal Portfolio

Live site: [emil-levin.github.io](https://emil-levin.github.io)

Personal portfolio and technical showcase for real-time 3D software, Unity projects, and C# tooling. Designed with a custom dark "service manual" aesthetic.

Single static page — `index.html` holds the markup, styles and script with no build step.

## Images

Full-resolution captures live in `assets/images/` and are never modified. The page loads
downscaled WebP copies from `assets/images/web/` (1.4 MB total, down from 53 MB of originals).

After adding or replacing a screenshot, regenerate them:

```sh
python3 tools/optimize-images.py
```

Files named `Screenshot ....png` are spare frames and are skipped by the script.
