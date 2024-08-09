

# cmem-plugin-reason

This [eccenca](https://eccenca.com) [Corporate Memory](https://documentation.eccenca.com) workflow plugin bundle contains plugins performing reasoning (Reason) and ontology consistency checking (Validate) using [ROBOT](http://robot.obolibrary.org/).

[![eccenca Corporate Memory](https://img.shields.io/badge/eccenca-Corporate%20Memory-orange)](https://documentation.eccenca.com) [![workflow](https://github.com/eccenca/cmem-plugin-pyshacl/actions/workflows/check.yml/badge.svg)](https://github.com/eccenca/cmem-plugin-pyshacl/actions) [![pypi version](https://img.shields.io/pypi/v/cmem-plugin-reason)](https://pypi.org/project/cmem-plugin-reason/) [![license](https://img.shields.io/pypi/l/cmem-plugin-reason)](https://pypi.org/project/cmem-plugin-reasom)

ROBOT is published under the [BSD 3-Clause "New" or "Revised" License](https://choosealicense.com/licenses/bsd-3-clause/).
Copyright © 2015, the Authors

## Build

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

# Reason
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
- [ELK](https://code.google.com/p/elk-reasoner/) (elk)
- [Expression Materializing Reasoner](http://static.javadoc.io/org.geneontology/expression-materializing-reasoner/0.1.3/org/geneontology/reasoner/ExpressionMaterializingReasoner.html) (emr)
- [HermiT](http://www.hermit-reasoner.com/) (hermit)
- [JFact](http://jfact.sourceforge.net/) (jfact)
- [Structural Reasoner](http://owlcs.github.io/owlapi/apidocs_4/org/semanticweb/owlapi/reasoner/structural/StructuralReasoner.html) (structural)
- [Whelk](https://github.com/balhoff/whelk) (whelk)

### Generated Axioms

By default, the reason operation will only assert inferred subclass axioms. The plugin provides the following 
parameters to include inferred axiom generators:

#### Class axiom generators
-  SubClass
- EquivalentClass
- DisjointClasses

#### Data property axiom generators
- DataPropertyCharacteristic
- EquivalentDataProperties
- SubDataProperty

#### Individual axiom generators
- ClassAssertion
- PropertyAssertion

#### Object property axiom generators
- EquivalentObjectProperty
- InverseObjectProperties
- ObjectPropertyCharacteristic
- SubObjectProperty
- ObjectPropertyRange
- ObjectPropertyDomain

### Validate OWL2 profiles

Validate the input ontology against OWL profiles (DL, EL, QL, RL, and Full). The ontology is annotated in the output graph. 

### Process valid OWL profiles from input

If enabled along with the "Validate OWL2 profiles" parameter, the list of valid profiles is taken from the plugin input, 
without validating the ontology against the profiles in the plugin. The inputs need to include the entity paths "profile"
for the valid profiles, and "ontology" for the ontology IRI, the latter overriding the setting in the "Reason" plugin.
If the "Validate OWL2 profiles" parameter is enabled in the "Validate" plugin, it can be directly connected to the input
of the "Reason" plugin.


### Maximum RAM Percentage

Maximum heap size for the Java virtual machine in the DI container running the reasoning process.

:warning: Setting the percentage too high may result in an out of memory error.

# Validate

The plugin outputs the explanation as text in Markdown format on the path "markdown",
the ontology IRI on the path "ontology", and (if enabled) the valid OWL2 profiles in the path "profile".

## Options

### Ontology graph IRI

The IRI of the input ontology graph. The graph IRI is selected from a list of graphs of type`owl:Ontology`.

### Reasoner

The following reasoner options are supported: 
- [ELK](https://code.google.com/p/elk-reasoner/) (elk)
- [Expression Materializing Reasoner](http://static.javadoc.io/org.geneontology/expression-materializing-reasoner/0.1.3/org/geneontology/reasoner/ExpressionMaterializingReasoner.html) (emr)
- [HermiT](http://www.hermit-reasoner.com/) (hermit)
- [JFact](http://jfact.sourceforge.net/) (jfact)
- [Structural Reasoner](http://owlcs.github.io/owlapi/apidocs_4/org/semanticweb/owlapi/reasoner/structural/StructuralReasoner.html) (structural)
- [Whelk](https://github.com/balhoff/whelk) (whelk)

### Produce output graph

If enabled, an explanation graph is created.

### Output graph IRI

The IRI of the output graph for the reasoning result.

:warning: Existing graphs will be overwritten.

### Write markdown explanation file

If enabled, an explanation markdown file is written to the project.

### Output filename

The filename of the Markdown file with the explanation of inconsistencies.

:warning: Existing files will be overwritten.

### Stop at inconsistencies
Raise an error if inconsistencies are found. If enabled, the plugin does not output entities.

### Validate OWL2 profiles

Validate the input ontology against OWL profiles (DL, EL, QL, RL, and Full). The valid profiles are added to the output 
Markdown file and the ontology is annotated in the output graph. The plugin outputs the profiles with path "profile",
and the ontology IRI with path "ontology".

### Maximum RAM Percentage

Maximum heap size for the Java virtual machine in the DI container running the reasoning process.

:warning: Setting the percentage too high may result in an out of memory error.