# Build the isolated, date-pinned reader library. Run once with R 4.4.2.

script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
if (length(script_arg) != 1) stop("bootstrap.R must be run with Rscript")
script_dir <- dirname(normalizePath(sub("^--file=", "", script_arg)))
source(file.path(script_dir, "versions.R"), local = TRUE)

actual_r <- as.character(getRversion())
if (!identical(actual_r, UW_R_VERSION)) {
  stop("This reader environment requires R ", UW_R_VERSION, "; found ", actual_r)
}

local_library <- file.path(script_dir, "library", paste0("R-", UW_R_VERSION))
dir.create(local_library, recursive = TRUE, showWarnings = FALSE)
.libPaths(c(local_library, .libPaths()))
options(repos = c(CRAN = UW_CRAN_SNAPSHOT))

# The snapshot freezes dependencies. bayesLife 5.3-0 itself was the GitHub
# version used by UW before 5.3-1 reached CRAN, so both reader packages are
# installed from immutable commits and verified byte-for-byte below.
available <- utils::available.packages(repos = UW_CRAN_SNAPSHOT, type = "source")
dependency_map <- tools::package_dependencies(
  names(UW_PACKAGE_VERSIONS),
  db = available,
  which = c("Depends", "Imports", "LinkingTo"),
  recursive = TRUE
)
dependencies <- unique(c("digest", unlist(dependency_map, use.names = FALSE)))
dependencies <- setdiff(
  dependencies,
  c(names(UW_PACKAGE_VERSIONS), "R", rownames(utils::installed.packages()))
)
if (length(dependencies)) {
  utils::install.packages(
    dependencies,
    lib = local_library,
    dependencies = FALSE,
    type = "source"
  )
}
if (!requireNamespace("digest", quietly = TRUE)) {
  stop("digest was not installed; exact package sources cannot be verified")
}

source_dir <- file.path(script_dir, "sources")
dir.create(source_dir, recursive = TRUE, showWarnings = FALSE)
source_files <- character(length(UW_PACKAGE_SOURCES))
names(source_files) <- names(UW_PACKAGE_SOURCES)
for (package in names(UW_PACKAGE_SOURCES)) {
  destination <- file.path(
    source_dir,
    paste0(package, "-", substr(UW_PACKAGE_REVISIONS[[package]], 1, 12), ".tar.gz")
  )
  if (!file.exists(destination)) {
    utils::download.file(
      UW_PACKAGE_SOURCES[[package]], destination, mode = "wb", quiet = FALSE
    )
  }
  actual_bytes <- unname(file.info(destination)$size)
  actual_sha256 <- digest::digest(destination, algo = "sha256", file = TRUE)
  if (!identical(actual_bytes, unname(UW_PACKAGE_SOURCE_BYTES[[package]])) ||
      !identical(actual_sha256, unname(UW_PACKAGE_SOURCE_SHA256[[package]]))) {
    stop(
      package, " source archive failed its pinned byte-length or SHA-256 check"
    )
  }
  source_files[[package]] <- destination
}

for (package in names(source_files)) {
  utils::install.packages(
    source_files[[package]], lib = local_library, repos = NULL,
    dependencies = FALSE, type = "source"
  )
}

for (package in names(UW_PACKAGE_VERSIONS)) {
  actual <- utils::packageDescription(package, lib.loc = local_library)$Version
  expected <- unname(UW_PACKAGE_VERSIONS[[package]])
  if (!identical(actual, expected)) {
    stop(package, " must be ", expected, "; the snapshot installed ", actual)
  }
}

installed <- as.data.frame(utils::installed.packages(lib.loc = local_library))
installed <- installed[order(installed$Package), c("Package", "Version", "Priority")]
utils::write.table(
  installed,
  file = file.path(script_dir, "installed-packages.tsv"),
  sep = "\t", quote = FALSE, row.names = FALSE
)
source_manifest <- data.frame(
  package = names(UW_PACKAGE_SOURCES),
  version = unname(UW_PACKAGE_VERSIONS),
  revision = unname(UW_PACKAGE_REVISIONS),
  bytes = unname(UW_PACKAGE_SOURCE_BYTES),
  sha256 = unname(UW_PACKAGE_SOURCE_SHA256),
  url = unname(UW_PACKAGE_SOURCES),
  stringsAsFactors = FALSE
)
utils::write.table(
  source_manifest,
  file = file.path(script_dir, "installed-source-manifest.tsv"),
  sep = "\t", quote = FALSE, row.names = FALSE
)
cat("Pinned UW reader library is ready at\n  ", local_library, "\n", sep = "")
