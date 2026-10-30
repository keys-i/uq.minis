/** Soft washes add real image detail without dividing the scenery into tiles */
import { useLayoutEffect, useRef, type RefObject } from "react";

export function Mist({
  waiting,
  poster,
  media,
  source,
  gentle,
  timer,
}: {
  waiting: boolean;
  poster?: string;
  media: RefObject<HTMLImageElement | HTMLVideoElement | null>;
  source?: string;
  gentle: boolean;
  timer: string;
}) {
  const veil = useRef<HTMLDivElement>(null),
    pixels = useRef<HTMLCanvasElement>(null),
    shown = useRef(""),
    fidelity = useRef(8);
  useLayoutEffect(() => {
    const layer = veil.current!,
      canvas = pixels.current!;
    let frame = 0,
      thumbnail: HTMLImageElement | undefined;
    const surfaces: HTMLCanvasElement[] = [];
    const clear = () => {
      delete layer.dataset.refining;
      layer.style.removeProperty("--clarity");
      canvas.style.removeProperty("opacity");
      canvas.width = canvas.height = 0;
      for (const surface of surfaces) surface.width = surface.height = 0;
    };
    const paint = (image: HTMLImageElement | HTMLVideoElement, native: boolean) => {
      const width = image instanceof HTMLVideoElement ? image.videoWidth : image.naturalWidth,
        height = image instanceof HTMLVideoElement ? image.videoHeight : image.naturalHeight;
      if (!width || !height) return;
      const context = canvas.getContext("2d"),
        sample = document.createElement("canvas"),
        brush = sample.getContext("2d"),
        wash = document.createElement("canvas"),
        fog = wash.getContext("2d");
      if (!context || !brush || !fog) return;
      // Two bounded display surfaces and one small sample, never a full upload-sized bitmap
      const ratio = Math.min(1, 960 / width, 540 / height);
      canvas.width = Math.max(1, Math.round(width * ratio));
      canvas.height = Math.max(1, Math.round(height * ratio));
      surfaces.push(sample, wash);
      const ceiling = Math.max(canvas.width, canvas.height),
        floor = Math.min(ceiling, native ? Math.max(8, fidelity.current) : 8),
        levels = [
          floor,
          ...[16, 32, 64, 128, 256, 512].filter((size) => size > floor && size < ceiling),
          ceiling,
        ];
      const sampleFrame = (size: number) => {
        const scale = Math.min(1, size / Math.max(width, height));
        sample.width = Math.max(1, Math.round(width * scale));
        sample.height = Math.max(1, Math.round(height * scale));
        brush.drawImage(image, 0, 0, sample.width, sample.height);
      };
      context.imageSmoothingEnabled = false;
      const draw = (size: number) => {
        sampleFrame(size);
        context.clearRect(0, 0, canvas.width, canvas.height);
        context.drawImage(sample, 0, 0, canvas.width, canvas.height);
      };
      canvas.style.opacity = native ? "1" : "0.78";
      if (gentle) {
        draw(Math.min(128, ceiling));
        return;
      }
      wash.width = canvas.width;
      wash.height = canvas.height;
      draw(floor);
      layer.dataset.refining = "";
      const started = performance.now(),
        duration = (levels.length - 1) * 180 + 160;
      let previous = -Infinity;
      const refine = (now: number) => {
        // A frame timestamp can precede the load callback that started this reveal
        const elapsed = Math.max(0, now - started),
          progress = Math.min(1, elapsed / duration);
        if (now - previous >= 32 || progress === 1) {
          previous = now;
          const step = Math.min(levels.length - 2, Math.floor(elapsed / 180)),
            blend = Math.min(1, (elapsed - step * 180) / 180);
          draw(levels[step]);
          sampleFrame(levels[step + 1]);
          fog.clearRect(0, 0, wash.width, wash.height);
          fog.globalCompositeOperation = "source-over";
          for (const [x, y] of [
            [0.22, 0.32],
            [0.78, 0.55],
            [0.45, 0.88],
          ]) {
            const radius = Math.max(1, ceiling * blend * 1.4),
              cloud = fog.createRadialGradient(
                x * wash.width,
                y * wash.height,
                0,
                x * wash.width,
                y * wash.height,
                radius,
              );
            cloud.addColorStop(0, `rgba(255,255,255,${blend})`);
            cloud.addColorStop(0.55, `rgba(255,255,255,${blend})`);
            cloud.addColorStop(1, "transparent");
            fog.fillStyle = cloud;
            fog.fillRect(0, 0, wash.width, wash.height);
          }
          fog.globalCompositeOperation = "source-in";
          fog.imageSmoothingEnabled = false;
          fog.drawImage(sample, 0, 0, wash.width, wash.height);
          context.drawImage(wash, 0, 0);
          fidelity.current = levels[step + 1];
          layer.style.setProperty("--clarity", String(native ? progress : progress * 0.45));
          if (native)
            canvas.style.opacity = String(1 - Math.max(0, (elapsed - duration + 160) / 160));
        }
        if (progress < 1) frame = requestAnimationFrame(refine);
        else {
          wash.width = wash.height = sample.width = sample.height = 0;
          if (native) clear();
          else delete layer.dataset.refining;
        }
      };
      frame = requestAnimationFrame(refine);
    };
    if (waiting) {
      fidelity.current = 8;
      if (poster) {
        thumbnail = new Image();
        thumbnail.referrerPolicy = "no-referrer";
        thumbnail.onload = () => paint(thumbnail!, false);
        thumbnail.src = poster;
      }
    } else if (source && media.current) {
      if (!gentle && shown.current !== source) paint(media.current, true);
      shown.current = source;
    }
    return () => {
      cancelAnimationFrame(frame);
      if (thumbnail) {
        thumbnail.onload = null;
        thumbnail.removeAttribute("src");
      }
      clear();
    };
  }, [waiting, poster, media, source, gentle]);
  return (
    <div ref={veil} className="timer-mist" aria-hidden="true" data-active={waiting || undefined}>
      <canvas ref={pixels} className="mist-pixels" width={0} height={0} />
      <div className="mist-haze" />
      <div className="mist-skeleton">
        <span className="skeleton-digits">{timer}</span>
        <div className="skeleton-player">
          <i />
          <i />
          <i />
          <span />
        </div>
      </div>
      <div className="mist-grains" />
    </div>
  );
}
