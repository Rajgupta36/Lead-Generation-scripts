type LogContext = Record<string, unknown>;

function write(level: string, message: string, context: LogContext = {}): void {
  process.stdout.write(`${JSON.stringify({ level, message, ...context, timestamp: new Date().toISOString() })}\n`);
}

export const logger = {
  info: (message: string, context?: LogContext) => write("info", message, context),
  warn: (message: string, context?: LogContext) => write("warn", message, context),
  error: (message: string, context?: LogContext) => write("error", message, context)
};
