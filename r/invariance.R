# EduMetria — invariância de medida para itens ordinais (lavaan, WLSMV).
# Sequência para dados categóricos (Wu & Estabrook, 2016): configural →
# limiares → limiares + cargas. Identificação "delta" padrão do lavaan.
# Uso: Rscript invariance.R <input.csv> <groups.csv> <output.json>
suppressPackageStartupMessages({ library(lavaan); library(jsonlite) })
args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 3)
X <- read.csv(args[1], check.names = FALSE)
X$group <- read.csv(args[2])$group
items <- setdiff(colnames(X), "group")
model <- paste("F =~", paste(items, collapse = " + "))
fit_one <- function(eq) cfa(model, data = X, group = "group", ordered = items, estimator = "WLSMV",
                            parameterization = "delta", group.equal = eq)
m_conf <- fit_one(character(0))
m_thr <- fit_one(c("thresholds"))
m_load <- fit_one(c("thresholds", "loadings"))
fm <- function(m) as.list(fitMeasures(m, c("chisq.scaled", "df.scaled", "cfi.scaled", "tli.scaled", "rmsea.scaled", "srmr")))
tests <- tryCatch(lavTestLRT(m_conf, m_thr, m_load), error = function(e) NULL)
res <- list(engine = paste0("lavaan ", packageVersion("lavaan")), groups = as.list(table(X$group)),
            configural = fm(m_conf), thresholds = fm(m_thr), thresholds_loadings = fm(m_load),
            lrt = if (is.null(tests)) NULL else as.data.frame(tests)[, c("Df", "Chisq diff", "Pr(>Chisq)")])
write_json(res, args[3], digits = NA, auto_unbox = TRUE, na = "null")
