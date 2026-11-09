"use client";

// Watches the live feed and, for new high or critical incidents: plays a tone
// (if sound is on), shows a desktop notification while the tab is in the
// background (if notifications are on and permitted), highlights the incidents
// in the queue, and announces them to screen readers. Both settings are off
// until the operator switches them on, and are remembered in this browser only.

import { useCallback, useEffect, useRef, useState } from "react";

import type { Incident } from "@/lib/api";
import {
  ALARM_INTERVAL_MS,
  AlertThrottle,
  FLASH_MS,
  alertLevel,
  alertMessage,
  newAlertingIncidents,
  playTone,
  unacknowledgedCritical,
} from "@/lib/alerting";

const SOUND_KEY = "resqivo.alerts.sound";
const NOTIFY_KEY = "resqivo.alerts.notifications";

export type NotificationSupport = "unsupported" | "default" | "granted" | "denied";

function stored(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === "on";
  } catch {
    return false;
  }
}

function store(key: string, on: boolean): void {
  try {
    window.localStorage.setItem(key, on ? "on" : "off");
  } catch {
    // Storage can be unavailable (private mode); the setting then lasts for this page only.
  }
}

function notificationSupport(): NotificationSupport {
  if (typeof window === "undefined" || typeof Notification === "undefined") return "unsupported";
  return Notification.permission as NotificationSupport;
}

export interface IncidentAlerts {
  sound: boolean;
  setSound: (on: boolean) => void;
  notifications: boolean;
  setNotifications: (on: boolean) => Promise<void>;
  notificationSupport: NotificationSupport;
  /** Incident IDs to highlight as new. */
  flashing: ReadonlySet<string>;
  /** The latest announcement, for an aria-live region. */
  announcement: string;
  /** Unacknowledged critical incidents that are not silenced. */
  alarm: { count: number; active: boolean };
  /** Silence the alarm until another critical incident arrives. */
  silence: () => void;
}

export function useIncidentAlerts(incidents: Incident[], loaded: boolean): IncidentAlerts {
  const [sound, setSoundState] = useState(false);
  const [notifications, setNotificationsState] = useState(false);
  const [support, setSupport] = useState<NotificationSupport>("unsupported");
  const [flashing, setFlashing] = useState<ReadonlySet<string>>(new Set());
  const [announcement, setAnnouncement] = useState("");
  const seen = useRef<Set<string> | null>(null);
  const audio = useRef<AudioContext | null>(null);
  const throttle = useRef(new AlertThrottle());
  const settings = useRef({ sound: false, notifications: false });
  const [silenced, setSilenced] = useState<ReadonlySet<string>>(new Set());

  // Read saved settings after mounting, so server and client render alike.
  useEffect(() => {
    const id = setTimeout(() => {
      const soundOn = stored(SOUND_KEY);
      const permission = notificationSupport();
      const notifyOn = stored(NOTIFY_KEY) && permission === "granted";
      settings.current = { sound: soundOn, notifications: notifyOn };
      setSoundState(soundOn);
      setNotificationsState(notifyOn);
      setSupport(permission);
    }, 0);
    return () => clearTimeout(id);
  }, []);

  const audioContext = useCallback((): AudioContext | null => {
    const Context =
      typeof window === "undefined"
        ? undefined
        : (window.AudioContext ??
          (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext);
    if (!Context) return null;
    audio.current ??= new Context();
    if (audio.current.state === "suspended") void audio.current.resume();
    return audio.current;
  }, []);

  // Browsers start audio only from a user gesture. After a reload with sound
  // remembered as on, unlock it on the operator's first click or key press.
  useEffect(() => {
    if (!sound) return;
    const unlock = () => {
      audioContext();
      window.removeEventListener("pointerdown", unlock);
      window.removeEventListener("keydown", unlock);
    };
    window.addEventListener("pointerdown", unlock);
    window.addEventListener("keydown", unlock);
    return () => {
      window.removeEventListener("pointerdown", unlock);
      window.removeEventListener("keydown", unlock);
    };
  }, [sound, audioContext]);

  const setSound = useCallback(
    (on: boolean) => {
      settings.current.sound = on;
      setSoundState(on);
      store(SOUND_KEY, on);
      // Switching on is a user gesture, which lets the browser start audio.
      if (on) {
        const context = audioContext();
        if (context) playTone(context, "confirm");
      }
    },
    [audioContext],
  );

  const setNotifications = useCallback(async (on: boolean) => {
    if (on && typeof Notification !== "undefined" && Notification.permission === "default") {
      await Notification.requestPermission();
    }
    const permission = notificationSupport();
    const enabled = on && permission === "granted";
    settings.current.notifications = enabled;
    setSupport(permission);
    setNotificationsState(enabled);
    store(NOTIFY_KEY, enabled);
  }, []);

  useEffect(() => {
    if (!loaded) return;
    const fresh = newAlertingIncidents(seen.current, incidents);
    seen.current = new Set(incidents.map((i) => i.incident_id));
    if (fresh.length === 0) return;

    const ids = fresh.map((i) => i.incident_id);
    const message = alertMessage(fresh);
    // Neither timer is cleared on cleanup: the feed is often refetched twice
    // in quick succession (the button and the live stream), and the second run
    // finds nothing new, so cancelling here would lose the highlight.
    setTimeout(() => {
      setFlashing((current) => new Set([...current, ...ids]));
      setAnnouncement(message);
    }, 0);
    setTimeout(() => {
      setFlashing((current) => new Set([...current].filter((id) => !ids.includes(id))));
    }, FLASH_MS);

    if (throttle.current.allow(Date.now())) {
      const level = alertLevel(fresh)!;
      if (settings.current.sound) {
        const context = audioContext();
        if (context) playTone(context, level);
      }
      if (
        settings.current.notifications &&
        typeof document !== "undefined" &&
        document.hidden &&
        notificationSupport() === "granted"
      ) {
        // Notification text is plain text; the browser does not render HTML in it.
        new Notification("RESQIVO simulation", { body: message, tag: "resqivo-incident" });
      }
    }
  }, [incidents, loaded, audioContext]);

  // The continuous alarm: repeats while unacknowledged critical incidents
  // remain that the operator has not silenced.
  const active = unacknowledgedCritical(incidents).filter((i) => !silenced.has(i.incident_id));
  const alarming = active.length > 0;
  useEffect(() => {
    if (!sound || !alarming) return;
    const timer = setInterval(() => {
      const context = audioContext();
      if (context) playTone(context, "critical");
    }, ALARM_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [sound, alarming, audioContext]);

  const silence = useCallback(() => {
    setSilenced(new Set(unacknowledgedCritical(incidents).map((i) => i.incident_id)));
  }, [incidents]);

  return {
    sound,
    setSound,
    notifications,
    setNotifications,
    notificationSupport: support,
    flashing,
    announcement,
    alarm: { count: active.length, active: alarming },
    silence,
  };
}
