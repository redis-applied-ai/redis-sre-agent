/** @type {import('@jest/types').Config.InitialOptions} */
module.exports = {
  transform: {
    '^.+\\.ts?$': 'ts-jest',
  },
  testMatch: ['<rootDir>/__tests__/**/*.spec.ts'],
  verbose: true,
  preset: 'ts-jest',
  testEnvironment: 'node',
  reporters: ['default'],
  moduleFileExtensions: ['js', 'json', 'ts'],
  modulePathIgnorePatterns: ['<rootDir>/dist'],
  modulePaths: ['<rootDir>/src'],
};
