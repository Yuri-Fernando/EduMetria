# EduMetria — modelo bifator/testlet (mirt::bfactor) vs. unidimensional.
# Uso: Rscript bifactor.R <input.csv> <specific.csv> <output.json>
# specific.csv: coluna "factor" (1 por item; NA = só fator geral).
suppressPackageStartupMessages({ library(mirt); library(jsonlite) })
args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 3)
X <- read.csv(args[1], check.names = FALSE)
spec <- read.csv(args[2])$factor
uni <- mirt(X, 1, itemtype = "2PL", verbose = FALSE, TOL = 1e-4)
bf <- bfactor(X, spec, itemtype = "2PL", verbose = FALSE, TOL = 1e-4)
cmp <- anova(uni, bf)
res <- list(engine = paste0("mirt ", packageVersion("mirt")),
            loglik = list(unidimensional = as.numeric(logLik(uni)), bifactor = as.numeric(logLik(bf))),
            aic = list(unidimensional = extract.mirt(uni, "AIC"), bifactor = extract.mirt(bf, "AIC")),
            bic = list(unidimensional = extract.mirt(uni, "BIC"), bifactor = extract.mirt(bf, "BIC")),
            lr_p = as.numeric(cmp$p[2]),
            general_slopes_uni = as.numeric(coef(uni, simplify = TRUE)$items[, "a1"]),
            general_slopes_bf = as.numeric(coef(bf, simplify = TRUE)$items[, "a1"]),
            items = colnames(X))
write_json(res, args[3], digits = NA, auto_unbox = TRUE, na = "null")
