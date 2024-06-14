# cmem-plugin-robotreason

Reasoning with ROBOT

This eccenca Corporate Memory workflow plugin performs reasoning using [ROBOT](http://robot.obolibrary.org/) (ROBOT is
an OBO Tool). It takes an OWL ontology and a data  graph as inputs and writes the reasoning result to a specified graph.

## Build

:warning: Before building, verify that **pyproject.toml** includes the following line in the `[tool.poetry]` section:
```
include = ["cmem_plugin_robotreason/bin/*"]
```


:bulb: Prior to the build process, the Java library _robot.jar_ (v1.9.4) and the _robot.sh_ script are automatically
downloaded from the [ROBOT GitHub repository](https://github.com/ontodev/robot). The _jar_ file is not downloaded if it
already exists in the same version. The ROBOT files are downloaded to the directory 
_cmem_plugin_robotreason/workflow/bin_ and are not removed automatically when running `task clean`. The files can be
removed with `task custom:clean_robot`.

```
➜ task clean build
```

## Installation

```
➜ cmemc admin workspace python install dist/*.tar.gz
```

Alternatively, the _build_ and _installation_ process can be initiated with the single command:

```
➜ task deploy
```

## Options

### Data graph IRI

The IRI of the input data graph. The graph IRI is selected from a list of graphs of types `di:Dataset`, `void:Dataset`
and `owl:Ontology`.

### Ontology graph IRI

The IRI of the input ontology graph. The graph IRI is selected from a list of graphs of type`owl:Ontology`.

### Result graph IRI

The IRI of the output graph for the reasoning result.

:warning: Existing graphs will be overwritten.


### Reasoner

The following reasoner options are supported: 
- elk ([ELK](https://code.google.com/p/elk-reasoner/))
- emr ([Expression Materializing Reasoner](http://static.javadoc.io/org.geneontology/expression-materializing-reasoner/0.1.3/org/geneontology/reasoner/ExpressionMaterializingReasoner.html))
- hermit ([HermiT](http://www.hermit-reasoner.com/))
- jfact ([JFact](http://jfact.sourceforge.net/))
- structural ([Structural Reasoner](http://owlcs.github.io/owlapi/apidocs_4/org/semanticweb/owlapi/reasoner/structural/StructuralReasoner.html))
- whelk ([Whelk](https://github.com/balhoff/whelk))



[![eccenca Corporate Memory](https://img.shields.io/badge/eccenca-Corporate%20Memory-orange)](https://documentation.eccenca.com)   
