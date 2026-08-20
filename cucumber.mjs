export default {
  format: [
    "progress",
    "html:reports/cucumber/cucumber-report.html",
    "json:reports/cucumber/cucumber-report.json",
    "junit:reports/cucumber/cucumber-junit.xml",
  ],
  import: [
    "./tsx-register.js",
    "features/support/**/*.ts",
    "features/steps/**/*.ts",
  ],
  paths: ["features/checkout/**/*.feature"],
  parallel: 1,
};
