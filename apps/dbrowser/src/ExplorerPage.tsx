// ExplorerPage.tsx
import * as React from "react";
import {
  useDataProvider,
  useNotify,
  useRedirect,
  useCreatePath,
  DataProvider,
  Identifier,
} from "react-admin";
import {
  Box,
  Breadcrumbs,
  Button,
  CircularProgress,
  Divider,
  Link,
  List as MUIList,
  ListItemButton,
  ListItemText,
  MenuItem,
  Select,
  SelectChangeEvent,
  Stack,
  TextField,
  Typography,
} from "@mui/material";

type FolderRecord = {
  id?: Identifier;

  // path fields
  dir: string; // e.g. "/photos/2025"
  parent_dir: string; // e.g. "/photos"
  name: string; // leaf name e.g. "2025"
  depth?: number;

  // counts
  file_count?: number;
  child_count?: number;

  // cross-browsing
  volume?: string; // optional
};

type GetListResult<T> = {
  data: T[];
  total?: number;
  pageInfo?: { hasPreviousPage: boolean; hasNextPage: boolean };
  meta?: any; // react-admin allows meta; your DP can return facet data here
};

/**
 * Meilisearch facet distributions look like:
 * {
 *   "ext": { "jpg": 120, "png": 12 },
 *   "camera_make": { "Apple": 90, "Canon": 22 }
 * }
 */
type FacetDistribution = Record<string, Record<string, number>>;
type FacetKey = "kind" | "ext" | "camera_make" | "camera_model";
type FacetSelection = Partial<Record<FacetKey, string[]>>;

// Choose whichever facets you want to show in Explorer.
const FACETS: FacetKey[] = ["kind", "ext", "camera_make", "camera_model"];

const splitDir = (dir: string): string[] =>
  dir && dir !== "/" ? dir.split("/").filter(Boolean) : [];

const joinDir = (parts: string[]): string =>
  parts.length ? `/${parts.join("/")}` : "/";

const formatCount = (n: number | undefined): string =>
  n == null ? "" : n.toLocaleString();

function toTitle(s: string): string {
  return s
    .replace(/_/g, " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());
}

export const ExplorerPage: React.FC = () => {
  const dataProvider = useDataProvider<DataProvider>();
  const notify = useNotify();
  const redirect = useRedirect();
  const createPath = useCreatePath();

  const [cwd, setCwd] = React.useState<string>("/");
  const [volume, setVolume] = React.useState<string>(""); // "" = all
  const [filterText, setFilterText] = React.useState<string>("");

  const [loading, setLoading] = React.useState<boolean>(false);
  const [folders, setFolders] = React.useState<FolderRecord[]>([]);

  // Facets state
  const [facetsLoading, setFacetsLoading] = React.useState<boolean>(false);
  const [facets, setFacets] = React.useState<FacetDistribution>({});
  const [facetSel, setFacetSel] = React.useState<FacetSelection>({});

  const parts = React.useMemo(() => splitDir(cwd), [cwd]);

  const breadcrumbItems = React.useMemo(() => {
    const crumbs: Array<{ label: string; dir: string }> = [{ label: "Root", dir: "/" }];
    const acc: string[] = [];
    for (const p of parts) {
      acc.push(p);
      crumbs.push({ label: p, dir: joinDir(acc) });
    }
    return crumbs;
  }, [parts]);

  const visibleFolders = React.useMemo(() => {
    const q = filterText.trim().toLowerCase();
    if (!q) return folders;
    return folders.filter((f) => (f.name || "").toLowerCase().includes(q));
  }, [folders, filterText]);

  const openFolder = (dir: string) => setCwd(dir);

  /**
   * This passes folder + volume + selected facets into the catfile list page.
   * Your catfile list dataProvider should interpret:
   *  - dir_prefix: prefix match on path/dir field
   *  - ext/kind/camera_make/camera_model: arrays => OR within same key, AND across keys
   */
  const openFilesHere = (dir: string) => {
    const filter = {
      dir_prefix: dir,
      ...(volume ? { volume } : {}),
      ...facetSel,
    };

    const search = encodeURIComponent(JSON.stringify(filter));
    const listPath = createPath({ resource: "catfile", type: "list" });
    redirect(`${listPath}?filter=${search}`);
  };

  const toggleFacet = (key: FacetKey, value: string) => {
    setFacetSel((prev) => {
      const cur = prev[key] ?? [];
      const next = cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value];
      const out: FacetSelection = { ...prev, [key]: next };
      if (next.length === 0) delete out[key];
      return out;
    });
  };

  const handleVolumeChange = (e: SelectChangeEvent<string>) => {
    setVolume(e.target.value);
  };

  const loadChildren = React.useCallback(async () => {
    setLoading(true);
    try {
      const parent_dir = cwd || "/";

      const res = (await dataProvider.getList("folders", {
        pagination: { page: 1, perPage: 200 },
        sort: { field: "name", order: "ASC" },
        filter: {
          parent_dir,
          ...(volume ? { volume } : {}),
        },
      })) as unknown as GetListResult<FolderRecord>;

      setFolders(res.data ?? []);
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error(e);
      notify("Failed to load folders", { type: "warning" });
      setFolders([]);
    } finally {
      setLoading(false);
    }
  }, [cwd, volume, dataProvider, notify]);

  /**
   * Load facet distributions for files under cwd (+ volume).
   *
   * Expectation:
   * - You implement a resource named "catfile_facets" in your dataProvider.
   * - It returns facetDistribution in res.meta.facets (recommended).
   *
   * Your dataProvider can forward `params.meta.facets` to Meilisearch as `facets: [...]`.
   */
  const loadFacets = React.useCallback(async () => {
    setFacetsLoading(true);
    try {
      const res = (await dataProvider.getList("catfile_facets", {
        pagination: { page: 1, perPage: 1 },
        sort: { field: "id", order: "ASC" },
        filter: {
          dir_prefix: cwd || "/",
          ...(volume ? { volume } : {}),
        },
        meta: { facets: FACETS },
      })) as unknown as GetListResult<any>;

      const fd = (res as any)?.meta?.facets as FacetDistribution | undefined;
      setFacets(fd ?? {});
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error(e);
      setFacets({});
    } finally {
      setFacetsLoading(false);
    }
  }, [cwd, volume, dataProvider]);

  // Reload folders + facets whenever cwd/volume changes
  React.useEffect(() => {
    void loadChildren();
    void loadFacets();
  }, [loadChildren, loadFacets]);

  const facetCard = (
    <Box
      sx={{
        width: { xs: "100%", md: 320 },
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        p: 1.25,
      }}
    >
      <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
        <Typography variant="subtitle2">Facets</Typography>
        <Stack direction="row" spacing={1}>
          <Button
            size="small"
            onClick={() => setFacetSel({})}
            disabled={Object.keys(facetSel).length === 0}
          >
            Clear
          </Button>
          <Button
            size="small"
            variant="outlined"
            onClick={() => openFilesHere(cwd)}
            disabled={facetsLoading}
          >
            Open with facets
          </Button>
        </Stack>
      </Stack>

      <Typography variant="caption" color="text.secondary">
        Filters apply to “Open files here” and “View files”.
      </Typography>

      <Divider sx={{ my: 1 }} />

      {facetsLoading ? (
        <Stack direction="row" spacing={1} alignItems="center">
          <CircularProgress size={18} />
          <Typography variant="body2">Loading facets…</Typography>
        </Stack>
      ) : (
        <Stack spacing={1.25}>
          {FACETS.map((k) => {
            const dist = facets[k] ?? {};
            const entries = Object.entries(dist)
              .filter(([val]) => val != null && String(val).trim() !== "")
              .sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0))
              .slice(0, 30); // keep panel usable

            if (entries.length === 0) return null;

            const selected = facetSel[k] ?? [];

            return (
              <Box key={k}>
                <Typography variant="body2" sx={{ fontWeight: 700, mb: 0.5 }}>
                  {toTitle(k)}
                </Typography>

                <MUIList dense disablePadding>
                  {entries.map(([val, count]) => {
                    const checked = selected.includes(val);
                    return (
                      <ListItemButton
                        key={`${k}:${val}`}
                        dense
                        onClick={() => toggleFacet(k, val)}
                        sx={{
                          borderRadius: 1,
                          mb: 0.25,
                          bgcolor: checked ? "action.selected" : "transparent",
                        }}
                      >
                        <ListItemText
                          primary={
                            <Stack direction="row" spacing={1} alignItems="baseline">
                              <Typography variant="body2">{val}</Typography>
                              <Typography variant="caption" color="text.secondary">
                                {count.toLocaleString()}
                              </Typography>
                            </Stack>
                          }
                        />
                        <Typography
                          variant="caption"
                          color={checked ? "primary" : "text.disabled"}
                          sx={{ fontWeight: 700, ml: 1 }}
                        >
                          {checked ? "✓" : ""}
                        </Typography>
                      </ListItemButton>
                    );
                  })}
                </MUIList>
              </Box>
            );
          })}

          {Object.keys(facets).length === 0 && (
            <Typography variant="body2" color="text.secondary">
              No facets available for this folder.
            </Typography>
          )}
        </Stack>
      )}
    </Box>
  );

  return (
    <Box sx={{ p: 2 }}>
      <Stack spacing={1.5}>
        <Typography variant="h5">Explorer</Typography>

        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems="center">
          <Box sx={{ flex: 1, width: "100%" }}>
            <Breadcrumbs aria-label="breadcrumb">
              {breadcrumbItems.map((c, idx) => {
                const isLast = idx === breadcrumbItems.length - 1;
                return isLast ? (
                  <Typography key={c.dir} color="text.primary">
                    {c.label}
                  </Typography>
                ) : (
                  <Link
                    key={c.dir}
                    underline="hover"
                    color="inherit"
                    href="#"
                    onClick={(ev) => {
                      ev.preventDefault();
                      ev.stopPropagation();
                      openFolder(c.dir);
                    }}
                  >
                    {c.label}
                  </Link>
                );
              })}
            </Breadcrumbs>
          </Box>

          <Select
            size="small"
            value={volume}
            displayEmpty
            onChange={handleVolumeChange}
            sx={{ minWidth: 180 }}
          >
            <MenuItem value="">All volumes</MenuItem>
            {/* Replace with real choices (volumes resource or your own facet endpoint) */}
            <MenuItem value="SYN_PHOTO">SYN_PHOTO</MenuItem>
            <MenuItem value="VOL2">VOL2</MenuItem>
          </Select>

          <TextField
            size="small"
            label="Filter folders"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            sx={{ minWidth: 220 }}
          />

          <Button variant="outlined" onClick={() => openFilesHere(cwd)} disabled={loading}>
            Open files here
          </Button>
        </Stack>

        <Divider />

        <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems="flex-start">
          {facetCard}

          <Box sx={{ flex: 1, width: "100%" }}>
            {loading ? (
              <Stack direction="row" spacing={1} alignItems="center">
                <CircularProgress size={20} />
                <Typography variant="body2">Loading…</Typography>
              </Stack>
            ) : (
              <MUIList dense disablePadding>
                {visibleFolders.length === 0 ? (
                  <Typography sx={{ p: 2 }} color="text.secondary">
                    No subfolders.
                  </Typography>
                ) : (
                  visibleFolders.map((f) => (
                    <ListItemButton
                      key={(f.id ?? f.dir) as React.Key}
                      onClick={(ev) => {
                        ev.preventDefault();
                        ev.stopPropagation();
                        openFolder(f.dir);
                      }}
                    >
                      <ListItemText
                        primary={
                          <Stack direction="row" spacing={1} alignItems="baseline">
                            <Typography sx={{ fontWeight: 600 }}>
                              {f.name || f.dir}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              {formatCount(f.file_count)} files
                              {f.child_count != null
                                ? `, ${formatCount(f.child_count)} folders`
                                : ""}
                            </Typography>
                          </Stack>
                        }
                        secondary={f.dir}
                      />

                      <Button
                        size="small"
                        onClick={(ev) => {
                          ev.preventDefault();
                          ev.stopPropagation(); // don’t trigger openFolder
                          openFilesHere(f.dir);
                        }}
                      >
                        View files
                      </Button>
                    </ListItemButton>
                  ))
                )}
              </MUIList>
            )}
          </Box>
        </Stack>
      </Stack>
    </Box>
  );
};
