# Change Log

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/) and this project adheres to [Semantic Versioning](https://semver.org/)

## [Unreleased]

### Added

 - defined input and output schema

### Fixed

 - incorrect stopping of workflow if "validate_profiles" and "stop_at_inconsistencies" is enabled in Validate plugin
 - fixed error when output graph is imported by input graph; the import is removed in-memory before reasoning

### Changed

- raise OSError on post result graph error
- removed write_md and produce_graph bool parameters
- if "input_profiles" is enabled the Reason plugin expects "ontology_iri" and "profile" on the input.
The ontology IRI on the input overrides the plugin setting.

## [1.0.0beta4] 2024-07-12

### Fixed

- fixed errors on CMEM instances with self-signed/invalid certificates

### Added

- valid OWL profiles can be read on the Reason plugin input instead of validating the ontology in the plugin

### Changed

- use DCMI Metadata Terms for provenance
- new icons

## [1.0.0beta3] 2024-07-09

### Fixed

- temporary files are now removed when an error occurs

### Added

- parameter for validating the input ontology against OWL2 profiles (DL, EL, QL, RL, and Full)
- Validate plugin outputs valid profiles with path "profile"

### Changed

- Validate plugin outputs the Markdown result with path "markdown"

## [1.0.0beta2] 2024-07-04

### Fixed

- `prov:wasGeneratedBy` in output graphs now refers to a plugin IRI instead of a literal

### Changed

- keep original output ("No explanations found.") if no inconsistencies found with Validate plugin
- provenance data in output graphs now includes plugin parameter settings
- new icons


## [1.0.0beta1] 2024-07-01

### Fixed

- valid range of "Maximum RAM Percentage" parameter in Validate plugin (1-100)

### Changed

- complete validation for IRI parameters
- remove "Annnotate inferred subclass axioms" parameter in Reason plugin

## [1.0.0alpha3] 2024-06-28

### Added

- "Annotate inferred axioms" parameter in Reason plugin
- "Maximum RAM percentage" parameter

### Changed

- axiom generators are now not advanced parameters

## [1.0.0alpha2] (skipped)

## [1.0.0alpha1] 2024-06-27

### Added

- initial version

