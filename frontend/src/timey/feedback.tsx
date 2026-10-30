/** Keep recovery and waiting beside the media, with the same material as its tools */
import { useEffect, useState } from "react";
import { Icon } from "../shared/icons.tsx";

export function Issue({
  title,
  message,
  children,
}: {
  title: string;
  message: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="timer-issue" role="alert">
      <Icon name="media" />
      <div>
        <strong>{title}</strong>
        <p>{message}</p>
        {children && <div className="timer-recovery">{children}</div>}
      </div>
    </div>
  );
}

export function Status({ text, cancel }: { text: string; cancel?: () => void }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    setSlow(false);
    const timer = setTimeout(() => setSlow(true), 8000);
    return () => clearTimeout(timer);
  }, [text]);
  return (
    <div className="timer-status" role="status" aria-atomic="true">
      <span className="status-seeds" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      <span>
        {text}
        {slow && <small>Taking a little longer - you can keep adjusting your timer</small>}
      </span>
      {cancel && (
        <button
          type="button"
          className="quiet"
          aria-label="Cancel"
          data-tip="Cancel"
          onClick={cancel}
        >
          <Icon name="close" />
        </button>
      )}
    </div>
  );
}

export function message(error: unknown, subject: string) {
  if (error instanceof TypeError)
    return `The connection dropped while ${subject}. Try again, or use a file from your device`;
  if (error instanceof Error) {
    if (/not a bot|blocking downloads|cookies-from-browser/i.test(error.message))
      return "YouTube is blocking this download. Connect Google and try again, or add a file from your device";
    if (
      /Cannot read this video|Couldn.t prepare this video|ffmpeg|Invalid data found/i.test(
        error.message,
      )
    )
      return "This file could not be decoded. Try another copy, or export it as MP4 for video, M4A for music, or PNG for a picture";
    return error.message;
  }
  return `Could not finish ${subject}. Try again or choose another file`;
}
