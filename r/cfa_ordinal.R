# EduMetria — CFA ordinal exploratória (lavaan, WLSMV). Roadmap P1.
# Uso: Rscript cfa_ordinal.R <input.csv> <output.json>
suppressPackageStartupMessages({ library(lavaan); library(jsonlite) })
args <- commandArgs(trailingOnly = TRUE)
X <- read.csv(args[1], check.names = FALSE)
items <- colnames(X)
model <- paste("F =~", paste(items, collapse = " + "))
fit <- cfa(model, data = X, ordered = items, estimator = "WLSMV", missing = "pairwise")
fm <- fitMeasures(fit, c("cfi.scaled", "tli.scaled", "rmsea.scaled", "srmr", "chisq.scaled", "df"))
std <- standardizedSolution(fit)
write_json(list(engine = paste0("lavaan ", packageVersion("lavaan")), fit_measures = as.list(fm),
                loadings = std[std$op == "=~", c("rhs", "est.std", "se")]), args[2], digits = NA, auto_unbox = TRUE)
