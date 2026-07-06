# Architecture Diagrams

The architecture is defined in [`workspace.dsl`](workspace.dsl) using the
[Structurizr DSL](https://docs.structurizr.com/dsl). The compiled workspace is stored in
[`workspace.json`](workspace.json) and can be used to restore the diagram layout in Structurizr.

## Exporting SVGs

**Start Structurizr:**

```bash
docker run -it --rm \
  -p 8080:8080 \
  --user $(id -u):$(id -g) \
  -v $(git rev-parse --show-toplevel)/docs:/usr/local/structurizr \
  structurizr/structurizr local
```

Then open [http://localhost:8080](http://localhost:8080) in your browser.

**Export a diagram as SVG:**

1. Open the diagram you want to export
2. Click the export button (top toolbar) → **Export diagram and key/legend to PNG/SVG**
3. Save the file to `docs/`
