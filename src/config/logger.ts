import winston from 'winston';

const {
  combine,
  timestamp,
  errors,
  json,
  colorize,
  printf,
} = winston.format;

const consoleFormat = printf(
  ({
    level,
    message,
    timestamp,
    stack,
  }) => {
    return `${timestamp} [${level}]: ${
      stack || message
    }`;
  },
);

export const logger =
  winston.createLogger({
    level: 'info',

    format: combine(
      timestamp(),
      errors({ stack: true }),
      json(),
    ),

    defaultMeta: {
      service: 'backend-api',
    },

    transports: [
      // Error Logs
      new winston.transports.File({
        filename:
          'logs/error.log',
        level: 'error',
      }),

      // Combined Logs
      new winston.transports.File({
        filename:
          'logs/combined.log',
      }),
    ],
  });

if (
  process.env.NODE_ENV !==
  'production'
) {
  logger.add(
    new winston.transports.Console({
      format: combine(
        colorize(),
        timestamp(),
        consoleFormat,
      ),
    }),
  );
}