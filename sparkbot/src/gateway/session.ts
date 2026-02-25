import * as fs from 'fs';
import * as path from 'path';
import { v4 as uuidv4 } from 'uuid';
import { Message } from '../providers/types';
import { RoutingTelemetry } from '../routing/router';

export interface SessionData {
  id: string;
  createdAt: string;
  updatedAt: string;
  history: Message[];
  compactionCount: number;
  routing_log: RoutingTelemetry[];
}

export class SessionManager {
  private sessionsDir: string;
  private current: SessionData | null = null;

  constructor(workspacePath: string) {
    this.sessionsDir = path.join(workspacePath, 'sessions');
    if (!fs.existsSync(this.sessionsDir)) {
      fs.mkdirSync(this.sessionsDir, { recursive: true });
    }
  }

  /**
   * Create a new session. Archives the current one if it exists.
   */
  newSession(): SessionData {
    if (this.current) {
      this.archiveSession();
    }

    this.current = {
      id: uuidv4(),
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      history: [],
      compactionCount: 0,
      routing_log: [],
    };
    this.save();
    return this.current;
  }

  /**
   * Get the current session, creating one if none exists.
   */
  getOrCreate(): SessionData {
    if (this.current) return this.current;

    // Try to load the latest session
    const latest = this.findLatestSession();
    if (latest) {
      this.current = latest;
      return this.current;
    }

    return this.newSession();
  }

  /**
   * Get the current session (may be null).
   */
  getCurrent(): SessionData | null {
    return this.current;
  }

  /**
   * Add a message to the current session.
   */
  addMessage(msg: Message): void {
    const session = this.getOrCreate();
    session.history.push(msg);
    session.updatedAt = new Date().toISOString();
    this.save();
  }

  /**
   * Add a routing telemetry entry.
   */
  addRoutingEntry(entry: RoutingTelemetry): void {
    const session = this.getOrCreate();
    session.routing_log.push(entry);
    this.save();
  }

  /**
   * Get routing log.
   */
  getRoutingLog(): RoutingTelemetry[] {
    return this.getOrCreate().routing_log || [];
  }


  /**
   * Replace the session history (after compaction).
   */
  setHistory(history: Message[]): void {
    const session = this.getOrCreate();
    session.history = history;
    session.compactionCount++;
    session.updatedAt = new Date().toISOString();
    this.save();
  }

  /**
   * Get conversation history.
   */
  getHistory(): Message[] {
    return this.getOrCreate().history;
  }

  /**
   * Archive the current session to a timestamped file.
   */
  archiveSession(): void {
    if (!this.current) return;

    const archiveDir = path.join(this.sessionsDir, 'archive');
    if (!fs.existsSync(archiveDir)) {
      fs.mkdirSync(archiveDir, { recursive: true });
    }

    const filename = `session-${this.current.id.substring(0, 8)}-${this.current.createdAt.replace(/[:.]/g, '-')}.json`;
    fs.writeFileSync(
      path.join(archiveDir, filename),
      JSON.stringify(this.current, null, 2),
      'utf-8',
    );

    this.current = null;
    // Remove active session file
    const activePath = path.join(this.sessionsDir, 'active.json');
    if (fs.existsSync(activePath)) fs.unlinkSync(activePath);
  }

  /**
   * Save current session to disk.
   */
  private save(): void {
    if (!this.current) return;
    const filePath = path.join(this.sessionsDir, 'active.json');
    fs.writeFileSync(filePath, JSON.stringify(this.current, null, 2), 'utf-8');
  }

  /**
   * Find the latest active session on disk.
   */
  private findLatestSession(): SessionData | null {
    const filePath = path.join(this.sessionsDir, 'active.json');
    if (!fs.existsSync(filePath)) return null;

    try {
      const data = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
      // Ensure all required fields exist (backward compatibility)
      if (!Array.isArray(data.history)) data.history = [];
      if (!Array.isArray(data.routing_log)) data.routing_log = [];
      if (typeof data.compactionCount !== 'number') data.compactionCount = 0;
      return data as SessionData;
    } catch {
      return null;
    }
  }
}
