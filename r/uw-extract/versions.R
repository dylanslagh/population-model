# Reader environment for the UW WPP2024-aligned archives.
#
# R 4.4.2 was current when these objects and package releases were produced.
# The dated repository freezes the complete dependency set; the two packages
# that define the serialized-object and accessor behavior are also checked by
# their literal DESCRIPTION versions before every export.

UW_R_VERSION <- "4.4.2"
UW_CRAN_SNAPSHOT <- "https://packagemanager.posit.co/cran/2024-11-11"
UW_PACKAGE_VERSIONS <- c(
  bayesTFR = "7.4-4",
  bayesLife = "5.3-0"
)
UW_PACKAGE_REVISIONS <- c(
  bayesTFR = "9c7116a00e8f6cb59956c859bee6659b65a574a4",
  bayesLife = "94780a40847a319b81e3c4dd4a01fa3b58dd733e"
)
UW_PACKAGE_SOURCES <- c(
  bayesTFR = paste0(
    "https://github.com/PPgp/bayesTFR/archive/",
    UW_PACKAGE_REVISIONS[["bayesTFR"]], ".tar.gz"
  ),
  bayesLife = paste0(
    "https://github.com/PPgp/bayesLife/archive/",
    UW_PACKAGE_REVISIONS[["bayesLife"]], ".tar.gz"
  )
)
UW_PACKAGE_SOURCE_BYTES <- c(
  bayesTFR = 2116877,
  bayesLife = 1946114
)
UW_PACKAGE_SOURCE_SHA256 <- c(
  bayesTFR = "8acec2ccf4c0c66f3bbbd23559d5bd13b44aaba48bae700113f4fbc760b91d58",
  bayesLife = "30cb9601ad8bc0c9e080a07de34e1b8769206295e153fa1c308c2ca5fa6084e1"
)
