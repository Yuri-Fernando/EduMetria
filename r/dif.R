# EduMetria — DIF de referência via mirt::multipleGroup + DIF (Wald/LRT).
# Uso: Rscript dif.R <input.csv> <groups.csv> <anchors.txt> <output.json>
suppressPackageStartupMessages({ library(mirt); library(jsonlite) })
args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 4)
X <- read.csv(args[1], check.names = FALSE)
g <- read.csv(args[2])$group
anchors <- readLines(args[3])
anchors <- anchors[nzchar(anchors)]
mg <- multipleGroup(X, 1, group = g, itemtype = "2PL",
                    invariance = c(anchors, "free_means", "free_var"), verbose = FALSE)
studied <- setdiff(colnames(X), anchors)
d <- DIF(mg, which.par = c("a1", "d"), items2test = studied, scheme = "add", p.adjust = "BH", verbose = FALSE)
write_json(list(engine = paste0("mirt ", packageVersion("mirt")), anchors = anchors,
                result = cbind(item = rownames(d), as.data.frame(d))), args[4], digits = NA, auto_unbox = TRUE)
