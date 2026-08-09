# Export one country's accessor-adjusted UW trajectories to transparent CSV.
#
# This intentionally does not use convert.*.trajectories: those public bulk
# converters write every country and round to five decimal places. The public
# get.* accessors below preserve full precision and apply stored WPP shifts.

script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
if (length(script_arg) != 1) stop("extract_one_country.R must be run with Rscript")
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
required <- c("tfr-dir", "e0-dir", "output-dir", "country-code", "iso3")
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
output_dir <- normalizePath(args[["output-dir"]], mustWork = FALSE)
country_code <- as.integer(args[["country-code"]])
iso3 <- toupper(trimws(args[["iso3"]]))
if (is.na(country_code) || nchar(iso3) != 3) stop("invalid country code or ISO3")
if (dir.exists(output_dir) && length(list.files(output_dir, all.files = TRUE, no.. = TRUE))) {
  stop("refusing to write into non-empty output directory: ", output_dir)
}
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

tfr_pred <- bayesTFR::get.tfr.prediction(sim.dir = tfr_dir)
e0_f_pred <- bayesLife::get.e0.prediction(sim.dir = e0_dir)
if (!bayesLife::has.e0.jmale.prediction(e0_f_pred)) {
  stop("the female e0 prediction does not contain UW's joint male prediction")
}
e0_m_pred <- bayesLife::get.e0.jmale.prediction(e0_f_pred)

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
country_row <- which(tfr_locations$loc_id == country_code)
if (length(country_row) != 1) stop("country is absent or duplicated in the UW objects")
country_name <- tfr_locations$name[[country_row]]

tfr <- as.matrix(bayesTFR::get.tfr.trajectories(tfr_pred, country_code))
e0_f <- as.matrix(bayesLife::get.e0.trajectories(e0_f_pred, country_code))
e0_m <- as.matrix(bayesLife::get.e0.trajectories(e0_m_pred, country_code))
expected_shape <- c(78L, 1000L)
for (item in list(tfr = tfr, e0_female = e0_f, e0_male = e0_m)) {
  if (!identical(dim(item), expected_shape)) {
    stop("each trajectory matrix must have shape 78 x 1000")
  }
  if (any(!is.finite(item))) stop("trajectory matrix contains non-finite values")
}
years <- as.integer(rownames(tfr))
if (!identical(years, 2023:2100) ||
    !identical(as.integer(rownames(e0_f)), years) ||
    !identical(as.integer(rownames(e0_m)), years)) {
  stop("all trajectory matrices must have row years 2023 through 2100")
}
if (any(tfr <= 0 | tfr > 15)) stop("TFR values failed broad plausibility bounds")
if (any(e0_f <= 0 | e0_f > 130) || any(e0_m <= 0 | e0_m > 130)) {
  stop("life-expectancy values failed broad plausibility bounds")
}

tfr_shift <- bayesTFR::get.tfr.shift(country_code, tfr_pred)
e0_f_shift <- bayesLife::get.e0.shift(country_code, e0_f_pred)
e0_m_shift <- bayesLife::get.e0.shift(country_code, e0_m_pred)
shifts <- list(tfr = tfr_shift, e0_female = e0_f_shift, e0_male = e0_m_shift)
for (component in names(shifts)) {
  value <- shifts[[component]]
  if (is.null(value) || !length(value) || any(!is.finite(value))) {
    stop(component, " has no finite stored WPP-alignment shift")
  }
}

old_options <- options(digits = 17, scipen = 999)
on.exit(options(old_options), add = TRUE)
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
shift_rows <- do.call(rbind, lapply(names(shifts), function(component) {
  value <- as.numeric(shifts[[component]])
  data.frame(component = component, shift_index = seq_along(value), value = value)
}))
utils::write.table(
  shift_rows, file = file.path(output_dir, "shifts.csv"), sep = ",",
  quote = TRUE, row.names = FALSE, col.names = TRUE, na = ""
)
writeLines(capture.output(sessionInfo()), file.path(output_dir, "session-info.txt"))

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
    ncol(tfr), nrow(tfr_locations), length(tfr_shift), length(e0_f_shift),
    length(e0_m_shift), "true"
  ),
  stringsAsFactors = FALSE
)
utils::write.table(
  r_metadata, file = file.path(output_dir, "r-metadata.tsv"), sep = "\t",
  quote = FALSE, row.names = FALSE, col.names = TRUE
)
cat("Exported ", country_name, " (", country_code, ") with ", ncol(tfr),
    " trajectories.\n", sep = "")
