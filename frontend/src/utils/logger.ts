"""Centralized logging utility with different log levels."""

import { LOG_LEVEL, LOG_LEVELS } from '@/config/env';

type LogLevel = keyof typeof LOG_LEVELS;

export interface LoggerOptions {
  prefix?: string;
  level?: LogLevel;
}

class Logger {
  private prefix: string;
  private level: number;

  constructor(options: LoggerOptions = {}) {
    this.prefix = options.prefix || '';
    this.level = LOG_LEVELS[options.level || 'DEBUG'];
  }

  private formatMessage(message: string): string {
    const timestamp = new Date().toISOString();
    const prefix = this.prefix ? `[${this.prefix}]` : '';
    return `${timestamp} ${prefix} ${message}`.trim();
  }

  private shouldLog(level: number): boolean {
    return level >= this.level;
  }

  debug(message: string, data?: any): void {
    if (this.shouldLog(LOG_LEVELS.DEBUG)) {
      const formatted = this.formatMessage(message);
      if (data) {
        console.debug(formatted, data);
      } else {
        console.debug(formatted);
      }
    }
  }

  info(message: string, data?: any): void {
    if (this.shouldLog(LOG_LEVELS.INFO)) {
      const formatted = this.formatMessage(message);
      if (data) {
        console.info(formatted, data);
      } else {
        console.info(formatted);
      }
    }
  }

  warn(message: string, data?: any): void {
    if (this.shouldLog(LOG_LEVELS.WARN)) {
      const formatted = this.formatMessage(message);
      if (data) {
        console.warn(formatted, data);
      } else {
        console.warn(formatted);
      }
    }
  }

  error(message: string, error?: Error | any): void {
    if (this.shouldLog(LOG_LEVELS.ERROR)) {
      const formatted = this.formatMessage(message);
      if (error) {
        console.error(formatted, error);
      } else {
        console.error(formatted);
      }
    }
  }

  group(label: string, fn: () => void): void {
    if (this.shouldLog(LOG_LEVELS.DEBUG)) {
      console.group(label);
      fn();
      console.groupEnd();
    }
  }

  time(label: string): () => void {
    console.time(label);
    return () => console.timeEnd(label);
  }
}

// Create default logger instance
export const logger = new Logger({ level: import.meta.env.DEV ? 'DEBUG' : 'WARN' });

/**
 * Create a logger with a specific prefix for a module.
 * @param moduleName - Name of the module
 * @returns Logger instance
 * @example
 * const log = createLogger('UserService');
 * log.info('User loaded');
 */
export function createLogger(moduleName: string): Logger {
  return new Logger({ prefix: moduleName });
}

/**
 * Create a performance monitoring logger.
 * @param label - Performance label
 * @returns Function to end timing
 * @example
 * const endTimer = measurePerformance('API Call');
 * // ... do work ...
 * endTimer();
 */
export function measurePerformance(label: string): () => void {
  const start = performance.now();
  return () => {
    const duration = performance.now() - start;
    logger.debug(`${label} took ${duration.toFixed(2)}ms`);
  };
}

export default logger;
