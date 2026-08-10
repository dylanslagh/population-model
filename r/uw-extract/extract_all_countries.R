# Export every UW location's accessor-adjusted trajectories, in one R session.
#
# This is extract_one_country.R with the loop moved inside R. That is the whole
# point: the two prediction objects take about two and a half minutes to load,
# so calling the single-country script 236 times spends ten hours reloading the
# same 1.8 GB. Loading once and iterating spends it once.
#
# Everything else is deliberately identical to the single-country path -- the
# same public accessors, the same full-precision output, the same five files per
# country -- so that the two can be checked against each other. The Python
# driver does exactly that: it re-exports Finland here and compares the file
# against the one produced by the single-country script.
#
# ISO3 codes are read from a file written out of the committed crosswalk. R does
# not get to invent them: a country code and an ISO3 code that disagree do not
# error anywhere downstream, they just project one country on another country's
# schedules.

script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
if (length(script_arg) != 1) stop("extract_all_countries.R must be run with Rscript")
script_dir <- dirname(normalizePath(sub("^--file=", "", script_arg)))
source(file.path(script_dir, "versions.R"), local = TRUE)

parse_args <- function(values) {
  result <- list()
  for (value in values) {
    if (!grepl("^--[^=]+=", value)) stop("arguments must use --name=value: ", value)
    pieces <- strsplit(sub("^--", "", value), "=", fixed = TRUE)[[1]]
    result[[pieces[[1]]]] <- paste(pieces[-1], collapse = "=")
  }
  result
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
required <- c("tfr-dir", "e0-dir", "output-root", "iso3-map")
missing <- required[!required %in% names(args)]
if (length(missing)) stop("missing argument(s): ", paste(missing, collapse = ", "))

actual_r <- as.character(getRversion())
if (!identical(actual_r, UW_R_VERSION)) {
  stop("Extractor requires R ", UW_R_VERSION, "; found ", actual_r)
}
local_library <- file.path(script_dir, "library", paste0("R-", UW_R_VERSION))
if (!dir.exists(local_library)) {
  stop("Pinned R library is missing; run r/uw-extract/bootstrap.R first")
}
.libPaths(c(local_library, .libPaths()))

for (package in names(UW_PACKAGE_VERSIONS)) {
  if (!requireNamespace(package, quietly = TRUE)) stop(package, " is not installed")
  actual <- utils::packageDescription(package)$Version
  expected <- unname(UW_PACKAGE_VERSIONS[[package]])
  if (!identical(actual, expected)) stop(package, " must be ", expected, "; found ", actual)
}

tfr_dir <- normalizePath(args[["tfr-dir"]], mustWork = TRUE)
e0_dir <- normalizePath(args[["e0-dir"]], mustWork = TRUE)
output_root <- normalizePath(args[["output-root"]], mustWork = FALSE)
iso3_map_path <- normalizePath(args[["iso3-map"]], mustWork = TRUE)
only <- if ("only" %in% names(args)) {
  as.integer(strsplit(args[["only"]], ",", fixed = TRUE)[[1]])
} else {
  NULL
}
dir.create(output_root, recursive = TRUE, showWarnings = FALSE)

iso3_map <- utils::read.csv(iso3_map_path, colClasses = c("integer", "character"))
if (!identical(names(iso3_map), c("loc_id", "iso3"))) {
  stop("the ISO3 map must have columns loc_id,iso3")
}
if (anyDuplicated(iso3_map$loc_id)) stop("the ISO3 map repeats a LocID")
iso3_for <- stats::setNames(toupper(trimws(iso3_map$iso3)), iso3_map$loc_id)

message("loading the UW prediction objects (this is the slow part)")
load_started <- Sys.time()
tfr_pred <- bayesTFR::get.tfr.prediction(sim.dir = tfr_dir)
e0_f_pred <- bayesLife::get.e0.prediction(sim.dir = e0_dir)
if (!bayesLife::has.e0.jmale.prediction(e0_f_pred)) {
  stop("the female e0 prediction does not contain UW's joint male prediction")
}
e0_m_pred <- bayesLife::get.e0.jmale.prediction(e0_f_pred)
message(sprintf(
  "loaded in %.1f seconds",
  as.numeric(difftime(Sys.time(), load_started, units = "secs"))
))

location_table <- function(prediction) {
  value <- bayesTFR::get.countries.table(prediction)
  result <- data.frame(
    loc_id = as.integer(value$code),
    name = as.character(value$name),
    stringsAsFactors = FALSE
  )
  result[order(result$loc_id), , drop = FALSE]
}
tfr_locations <- location_table(tfr_pred)
e0_f_locations <- location_table(e0_f_pred)
e0_m_locations <- location_table(e0_m_pred)
if (nrow(tfr_locations) != 236L || anyDuplicated(tfr_locations$loc_id)) {
  stop("TFR object must contain 236 unique locations")
}
if (!identical(tfr_locations$loc_id, e0_f_locations$loc_id) ||
    !identical(tfr_locations$loc_id, e0_m_locations$loc_id)) {
  stop("TFR, female e0, and male e0 location codes do not match")
}

unmapped <- setdiff(tfr_locations$loc_id, as.integer(names(iso3_for)))
if (length(unmapped)) {
  stop("no ISO3 code supplied for LocID(s): ", paste(unmapped, collapse = ", "))
}

shift_rows_for <- function(shifts) {
  do.call(rbind, lapply(names(shifts), function(component) {
    value <- as.numeric(shifts[[component]])
    data.frame(component = component, shift_index = seq_along(value), value = value)
  }))
}

session_lines <- capture.output(sessionInfo())
old_options <- options(digits = 17, scipen = 999)
on.exit(options(old_options), add = TRUE)

codes <- tfr_locations$loc_id
if (!is.null(only)) {
  unknown <- setdiff(only, codes)
  if (length(unknown)) stop("unknown LocID(s): ", paste(unknown, collapse = ", "))
  codes <- only
}

written <- 0L
skipped <- 0L
started <- Sys.time()
for (country_code in codes) {
  output_dir <- file.path(output_root, as.character(country_code))
  done_marker <- file.path(output_dir, "r-metadata.tsv")
  if (file.exists(done_marker)) {
    skipped <- skipped + 1L
    next
  }
  # Resumable, but never by half: a directory that exists without the marker is
  # a previous run that died partway through and its contents cannot be trusted.
  if (dir.exists(output_dir)) unlink(output_dir, recursive = TRUE)
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

  country_row <- which(tfr_locations$loc_id == country_code)
  if (length(country_row) != 1) stop("country is absent or duplicated in the UW objects")
  country_name <- tfr_locations$name[[country_row]]
  iso3 <- unname(iso3_for[[as.character(country_code)]])
  if (is.null(iso3) || nchar(iso3) != 3) stop("invalid ISO3 for LocID ", country_code)

  tfr <- as.matrix(bayesTFR::get.tfr.trajectories(tfr_pred, country_code))
  e0_f <- as.matrix(bayesLife::get.e0.trajectories(e0_f_pred, country_code))
  e0_m <- as.matrix(bayesLife::get.e0.trajectories(e0_m_pred, country_code))
  expected_shape <- c(78L, 1000L)
  for (item in list(tfr = tfr, e0_female = e0_f, e0_male = e0_m)) {
    if (!identical(dim(item), expected_shape)) {
      stop("each trajectory matrix must have shape 78 x 1000 (LocID ", country_code, ")")
    }
    if (any(!is.finite(item))) {
      stop("trajectory matrix contains non-finite values (LocID ", country_code, ")")
    }
  }
  years <- as.integer(rownames(tfr))
  if (!identical(years, 2023:2100) ||
      !identical(as.integer(rownames(e0_f)), years) ||
      !identical(as.integer(rownames(e0_m)), years)) {
    stop("all trajectory matrices must have row years 2023 through 2100")
  }
  if (any(tfr <= 0 | tfr > 15)) {
    stop("TFR values failed broad plausibility bounds (LocID ", country_code, ")")
  }
  if (any(e0_f <= 0 | e0_f > 130) || any(e0_m <= 0 | e0_m > 130)) {
    stop("life-expectancy values failed plausibility bounds (LocID ", country_code, ")")
  }

  shifts <- list(
    tfr = bayesTFR::get.tfr.shift(country_code, tfr_pred),
    e0_female = bayesLife::get.e0.shift(country_code, e0_f_pred),
    e0_male = bayesLife::get.e0.shift(country_code, e0_m_pred)
  )
  for (component in names(shifts)) {
    value <- shifts[[component]]
    if (is.null(value) || !length(value) || any(!is.finite(value))) {
      stop(component, " has no finite stored shift (LocID ", country_code, ")")
    }
  }

  trajectory_id <- rep(seq_len(ncol(tfr)), each = nrow(tfr))
  export <- data.frame(
    loc_id = rep(country_code, length(trajectory_id)),
    country = rep(country_name, length(trajectory_id)),
    iso3 = rep(iso3, length(trajectory_id)),
    year = rep(years, times = ncol(tfr)),
    trajectory_id = trajectory_id,
    tfr = as.vector(tfr),
    e0_female = as.vector(e0_f),
    e0_male = as.vector(e0_m),
    stringsAsFactors = FALSE
  )
  utils::write.table(
    export, file = file.path(output_dir, "trajectories.csv"), sep = ",",
    quote = TRUE, row.names = FALSE, col.names = TRUE, na = ""
  )
  utils::write.table(
    tfr_locations, file = file.path(output_dir, "locations.csv"), sep = ",",
    quote = TRUE, row.names = FALSE, col.names = TRUE, na = ""
  )
  utils::write.table(
    shift_rows_for(shifts), file = file.path(output_dir, "shifts.csv"), sep = ",",
    quote = TRUE, row.names = FALSE, col.names = TRUE, na = ""
  )
  writeLines(session_lines, file.path(output_dir, "session-info.txt"))

  r_metadata <- data.frame(
    key = c(
      "R_version", "bayesTFR_version", "bayesLife_version", "loc_id", "iso3",
      "country", "year_start", "year_end", "year_count", "trajectories",
      "locations", "tfr_shift_count", "e0_female_shift_count",
      "e0_male_shift_count", "accessor_shifts_applied"
    ),
    value = c(
      actual_r,
      utils::packageDescription("bayesTFR")$Version,
      utils::packageDescription("bayesLife")$Version,
      country_code, iso3, country_name, min(years), max(years), length(years),
      ncol(tfr), nrow(tfr_locations), length(shifts$tfr),
      length(shifts$e0_female), length(shifts$e0_male), "true"
    ),
    stringsAsFactors = FALSE
  )
  # Written last: this file is what marks the directory complete.
  utils::write.table(
    r_metadata, file = file.path(output_dir, "r-metadata.tsv"), sep = "\t",
    quote = FALSE, row.names = FALSE, col.names = TRUE
  )

  written <- written + 1L
  if (written %% 20L == 0L) {
    message(sprintf(
      "  %d written, %d skipped, %.1f minutes elapsed",
      written, skipped,
      as.numeric(difftime(Sys.time(), started, units = "mins"))
    ))
  }
}

cat("Exported ", written, " countries (", skipped, " already present).\n", sep = "")
