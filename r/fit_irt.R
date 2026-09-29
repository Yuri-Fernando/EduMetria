# EduMetria — worker psicométrico de referência (R + mirt).
# Uso: Rscript fit_irt.R <input.csv> <output.json> <family: 2pl|1pl|grm> <seed>
# Entrada: matriz pessoa x item (NA = não observado). Saída: JSON com
# parâmetros slope-intercept (a, d) e tradicionais (a, b), logLik, convergência
# e EAP. Nenhum comando/caminho arbitrário do cliente chega aqui: o adapter
# Python só aceita famílias da allowlist e arquivos que ele mesmo criou.
suppressPackageStartupMessages({ library(mirt); library(jsonlite) })
args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 4)
inp <- args[1]; out <- args[2]; family <- args[3]; seed <- as.integer(args[4])
stopifnot(family %in% c("2pl", "1pl", "grm"))
set.seed(seed)
X <- read.csv(inp, check.names = FALSE)
itemtype <- switch(family, "2pl" = "2PL", "1pl" = "2PL", "grm" = "graded")
model <- if (family == "1pl") {
  mirt.model(sprintf("F = 1-%d\nCONSTRAIN = (1-%d, a1)", ncol(X), ncol(X)))
} else 1
fit <- mirt(X, model = model, itemtype = itemtype, SE = TRUE, SE.type = "crossprod",
            quadpts = 61, TOL = 1e-4, technical = list(NCYCLES = 2000), verbose = FALSE)
si <- coef(fit, simplify = TRUE)$items
irt <- coef(fit, IRTpars = TRUE, simplify = TRUE)$items
sc <- fscores(fit, method = "EAP", full.scores.SE = TRUE)
se_tab <- coef(fit, printSE = TRUE, as.data.frame = TRUE)
res <- list(
  engine = paste0("mirt ", as.character(packageVersion("mirt"))),
  r_version = R.version.string,
  family = family,
  loglik = as.numeric(logLik(fit)),
  converged = extract.mirt(fit, "converged"),
  iterations = extract.mirt(fit, "iterations"),
  items = colnames(X),
  slope_intercept = as.data.frame(si),
  irt_pars = as.data.frame(irt),
  eap = as.numeric(sc[, 1]),
  eap_se = as.numeric(sc[, 2]),
  se_table = data.frame(par = rownames(se_tab), est = se_tab[, 1], se = se_tab[, 2])
)
write_json(res, out, digits = NA, auto_unbox = TRUE, na = "null")
