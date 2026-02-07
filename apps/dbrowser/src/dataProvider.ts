import { Meilisearch } from "meilisearch";
import type { Identifier } from "react-admin";

export type FolderRecord = {
  id: Identifier; // required by react-admin
  dir: string; // "/photos/2025"
  parent_dir: string; // "/photos"
  name: string; // "2025"
  depth?: number;

  file_count?: number;
  child_count?: number;

  volume?: string; // optional, depending on your model
};

const PROJECT_CODE = "BLDR";
const PROXY_BASE = "/api/external";
const API_TOKEN =
  "7925cbb294bc45a4927e8a0f39a9f74308ca68bef878fa2b30f1b07a1302cb87"; // keep secrets server-side in real apps
const buildProxyUrl = (targetUrl: string, extra = {}) => {
  const params = new URLSearchParams({
    header_Token: API_TOKEN,
    target_url: targetUrl,
    ...extra,
  });
  return `${PROXY_BASE}?${params.toString()}`;
};

interface DefectRecord {
  id?: number;
  title?: string;
  actual_result?: string;
}

interface DefectCreateParams {
  id: number;
  data: {
    title: string;
    actual_result: string;
    status: string;
    severity: string;
  };
}

/*
type DataProvider = {
  create: (params: unknown) => Promise<unknown>;
  update: (params: unknown) => Promise<unknown>;
  delete: (params: unknown) => Promise<unknown>;
  getOne: (params: unknown) => Promise<unknown>;
  getList: (params: unknown) => Promise<unknown>;
};

 */
const MEILI_URL = "https://meili.bldrdojo.com";
const MEILI_API_KEY = "DKKeyDKKeyDkKeyDKKey";
const INDEX_NAME = "files_catalog";
const FOLDERS_INDEX_NAME = "catalog_folders";

export const travelListTagProvider = {
  getList: async (params: Record<string, unknown>) => {
    try {
      const target = `http://localhost:8000/api/travellist/tag/`;
      let url = buildProxyUrl(target, {
        ...{ limit: String(100), offset: String(0) },
        ...params,
      });
      url = "http://localhost:8020" + url;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`GET cases failed: ${res.status}`);
      const data = await res.json();
      return {
        data: data.results,
        pageInfo: { hasPreviousPage: false, hasNextPage: false },
      };
    } catch (e) {
      console.log(e);
      //setError(String(e));
    } finally {
      //setSavingId(null);
    }
  },
  delete: async (params: Record<string, unknown>) => {
    try {
      console.log(params);
      const target = `http://localhost:8000/api/travellist/category/${params.id}/`;
      const res = await fetch("http://localhost:8020" + buildProxyUrl(target), {
        method: "DELETE",
        headers: { "content-type": "application/json" },
      });
      const data = await res.json();
      return { data: { id: data.result.id } };
    } catch (e) {
      console.log(String(e));
    }
  },
  deleteMany: async (params: {
    ids: number[];
  }): Promise<{ data: number[] | undefined }> => {
    try {
      const ids: number[] = params.ids;
      const target = `http://localhost:8000/api/travellist/category/bulk_delete/`;
      const raw_body = {
        ids,
        // If your Qase requires more fields (e.g., severity, suite_id), add them here.
      };
      const body = JSON.stringify(raw_body);
      const res = await fetch("http://localhost:8020" + buildProxyUrl(target), {
        method: "DELETE",
        headers: { "content-type": "application/json" },
        body,
      });

      if (!res.ok) {
        const t = await res.text().catch(() => "");
        throw new Error(`POST failed: ${res.status} ${t}`);
      }
      return { data: ids };
    } catch (e) {
      console.log(String(e));
      return { data: undefined };
    }
  },
};

export const travelListCategoryProvider = {
  getList: async (params: Record<string, unknown>) => {
    console.log("Getting TraveList");
    try {
      const target = `http://localhost:8000/api/travellist/category/`;
      let url = buildProxyUrl(target, {
        ...{ limit: String(100), offset: String(0) },
        ...params,
      });
      url = "http://localhost:8020" + url;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`GET cases failed: ${res.status}`);
      const data = await res.json();
      return {
        data: data.results,
        pageInfo: { hasPreviousPage: false, hasNextPage: false },
      };
    } catch (e) {
      console.log(e);
      //setError(String(e));
    } finally {
      //setSavingId(null);
    }
  },
  delete: async (params: Record<string, unknown>) => {
    try {
      console.log(params);
      const target = `http://localhost:8000/api/travellist/category/${params.id}/`;
      const res = await fetch("http://localhost:8020" + buildProxyUrl(target), {
        method: "DELETE",
        headers: { "content-type": "application/json" },
      });
      const data = await res.json();
      return { data: { id: data.result.id } };
    } catch (e) {
      console.log(String(e));
    }
  },
  deleteMany: async (params: {
    ids: number[];
  }): Promise<{ data: number[] | undefined }> => {
    try {
      const ids: number[] = params.ids;
      const target = `http://localhost:8000/api/travellist/category/bulk_delete/`;
      const raw_body = {
        ids,
        // If your Qase requires more fields (e.g., severity, suite_id), add them here.
      };
      const body = JSON.stringify(raw_body);
      const res = await fetch("http://localhost:8020" + buildProxyUrl(target), {
        method: "DELETE",
        headers: { "content-type": "application/json" },
        body,
      });

      if (!res.ok) {
        const t = await res.text().catch(() => "");
        throw new Error(`POST failed: ${res.status} ${t}`);
      }
      return { data: ids };
    } catch (e) {
      console.log(String(e));
      return { data: undefined };
    }
  },
  create: async (params: any) => {
    try {
      const target = `http://localhost:8000/api/travellist/category/`;
      const raw_body = {
        name: params.data.name.trim(),
        // If your Qase requires more fields (e.g., severity, suite_id), add them here.
      };
      const body = JSON.stringify(raw_body);

      const res = await fetch("http://localhost:8020" + buildProxyUrl(target), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body,
      });

      if (!res.ok) {
        const t = await res.text().catch(() => "");
        throw new Error(`POST failed: ${res.status} ${t}`);
      }
      const data = await res.json();
      const response: DefectRecord = {};
      response["id"] = data.id;
      response["name"] = data.name;
      return { data: response };
    } catch (e) {
      console.log(e);
    } finally {
      //setAddBusy(false);
    }
  },
};

export const travelListListItemProvider = {
  getList: async (params: Record<string, unknown>) => {
    try {
      const target = `http://localhost:8000/api/travellist/listitem/`;
      let url = buildProxyUrl(target, {
        ...{ limit: String(100), offset: String(0) },
        ...params,
      });
      url = "http://localhost:8020" + url;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`GET cases failed: ${res.status}`);
      const data = await res.json();
      return {
        data: data.results,
        pageInfo: { hasPreviousPage: false, hasNextPage: false },
      };
    } catch (e) {
      console.log(e);
      //setError(String(e));
    } finally {
      //setSavingId(null);
    }
  },
  updateMany: async (params: any) => {
    console.log("Params (IDs and Data):", params);
    // Data Provider methods MUST return a promise that resolves to { data: [...] }
    try {
      const ids: number[] = params.ids;
      const target = `http://localhost:8000/api/travellist/listitem/bulk_update/`;
      const raw_body = {
        ids,
        data:params.data
        // If your Qase requires more fields (e.g., severity, suite_id), add them here.
      };
      const body = JSON.stringify(raw_body);
      const res = await fetch("http://localhost:8020" + buildProxyUrl(target), {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body,
      });

      if (!res.ok) {
        const t = await res.text().catch(() => "");
        throw new Error(`POST failed: ${res.status} ${t}`);
      }
      return { data: ids };
    } catch (e) {
      console.log(String(e));
      return { data: undefined };
    }
  },
  delete: async (params: Record<string, unknown>) => {
    try {
      console.log(params);
      const target = `http://localhost:8000/api/travellist/item/${params.id}/`;
      const res = await fetch("http://localhost:8020" + buildProxyUrl(target), {
        method: "DELETE",
        headers: { "content-type": "application/json" },
      });
      const data = await res.json();
      return { data: { id: data.result.id } };
    } catch (e) {
      console.log(String(e));
    }
  },
  deleteMany: async (params: {
    ids: number[];
  }): Promise<{ data: number[] | undefined }> => {
    try {
      const ids: number[] = params.ids;
      const target = `http://localhost:8000/api/travellist/item/bulk_delete/`;
      const raw_body = {
        ids,
        // If your Qase requires more fields (e.g., severity, suite_id), add them here.
      };
      const body = JSON.stringify(raw_body);
      const res = await fetch("http://localhost:8020" + buildProxyUrl(target), {
        method: "DELETE",
        headers: { "content-type": "application/json" },
        body,
      });

      if (!res.ok) {
        const t = await res.text().catch(() => "");
        throw new Error(`POST failed: ${res.status} ${t}`);
      }
      return { data: ids };
    } catch (e) {
      console.log(String(e));
      return { data: undefined };
    }
  },
  create: async (params: any) => {
    try {
      const target = `http://localhost:8000/api/travellist/item/`;
      const raw_body = {
        name: params.data.name.trim(),
        category: params.data.category ?? null,
        tags: params.data.tags ?? [],
        // If your Qase requires more fields (e.g., severity, suite_id), add them here.
      };
      const body = JSON.stringify(raw_body);

      const res = await fetch("http://localhost:8020" + buildProxyUrl(target), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body,
      });

      if (!res.ok) {
        const t = await res.text().catch(() => "");
        throw new Error(`POST failed: ${res.status} ${t}`);
      }
      const data = await res.json();
      const response: DefectRecord = {};
      response["id"] = data.id;
      response["name"] = data.name;
      return { data: response };
    } catch (e) {
      console.log(e);
    } finally {
      //setAddBusy(false);
    }
  },
};

export const travelListItemProvider = {
  getList: async (params: Record<string, unknown>) => {
    console.log("Getting TraveList");
    try {
      const target = `http://localhost:8000/api/travellist/item/`;
      let url = buildProxyUrl(target, {
        ...{ limit: String(100), offset: String(0) },
        ...params,
      });
      url = "http://localhost:8020" + url;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`GET cases failed: ${res.status}`);
      const data = await res.json();
      return {
        data: data.results,
        pageInfo: { hasPreviousPage: false, hasNextPage: false },
      };
    } catch (e) {
      console.log(e);
      //setError(String(e));
    } finally {
      //setSavingId(null);
    }
  },
  delete: async (params: Record<string, unknown>) => {
    try {
      console.log(params);
      const target = `http://localhost:8000/api/travellist/item/${params.id}/`;
      const res = await fetch("http://localhost:8020" + buildProxyUrl(target), {
        method: "DELETE",
        headers: { "content-type": "application/json" },
      });
      const data = await res.json();
      return { data: { id: data.result.id } };
    } catch (e) {
      console.log(String(e));
    }
  },
  deleteMany: async (params: {
    ids: number[];
  }): Promise<{ data: number[] | undefined }> => {
    try {
      const ids: number[] = params.ids;
      const target = `http://localhost:8000/api/travellist/item/bulk_delete/`;
      const raw_body = {
        ids,
        // If your Qase requires more fields (e.g., severity, suite_id), add them here.
      };
      const body = JSON.stringify(raw_body);
      const res = await fetch("http://localhost:8020" + buildProxyUrl(target), {
        method: "DELETE",
        headers: { "content-type": "application/json" },
        body,
      });

      if (!res.ok) {
        const t = await res.text().catch(() => "");
        throw new Error(`POST failed: ${res.status} ${t}`);
      }
      return { data: ids };
    } catch (e) {
      console.log(String(e));
      return { data: undefined };
    }
  },
  create: async (params: any) => {
    try {
      const target = `http://localhost:8000/api/travellist/item/`;
      const raw_body = {
        name: params.data.name.trim(),
        category: params.data.category ?? null,
        tags: params.data.tags ?? [],
        // If your Qase requires more fields (e.g., severity, suite_id), add them here.
      };
      const body = JSON.stringify(raw_body);

      const res = await fetch("http://localhost:8020" + buildProxyUrl(target), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body,
      });

      if (!res.ok) {
        const t = await res.text().catch(() => "");
        throw new Error(`POST failed: ${res.status} ${t}`);
      }
      const data = await res.json();
      const response: DefectRecord = {};
      response["id"] = data.id;
      response["name"] = data.name;
      return { data: response };
    } catch (e) {
      console.log(e);
    } finally {
      //setAddBusy(false);
    }
  },
};

export const foldersDataProvider = {
  getList: async (params: Record<string, any>) => {
    const client = new Meilisearch({
      host: MEILI_URL,
      apiKey: MEILI_API_KEY,
    });

    const index = client.index(FOLDERS_INDEX_NAME);

    // --- pagination (react-admin style) ---
    const page = Number(params.pagination?.page ?? 1);
    const perPage = Number(params.pagination?.perPage ?? 200);
    const offset = (page - 1) * perPage;

    // --- sorting ---
    const sortField = params.sort?.field ?? "name";
    const sortOrder = String(params.sort?.order ?? "ASC").toLowerCase();
    const sort: string[] = [`${sortField}:${sortOrder}`];

    // --- filters ---
    const filterObj = params.filter ?? {};
    const clauses: string[] = [];

    // Explorer drill-down expects parent_dir (root uses "/")
    const parentDir = (filterObj.parent_dir ?? "/") as string;
    clauses.push(`parent_dir = "${escapeMeiliString(parentDir)}"`);

    // Optional cross-browsing filter
    if (filterObj.volume) {
      clauses.push(`volume = "${escapeMeiliString(String(filterObj.volume))}"`);
    }

    // Optional depth filter if you want
    if (filterObj.depth != null && filterObj.depth !== "") {
      clauses.push(`depth = ${Number(filterObj.depth)}`);
    }

    const meiliFilter = clauses.length ? clauses.join(" AND ") : undefined;

    const res = await index.search<FolderRecord>("", {
      limit: perPage,
      offset,
      sort,
      filter: meiliFilter,
    });

    const data: FolderRecord[] = (res.hits ?? []).map((h: any) => ({
      ...h,
      // ensure id exists (if you use dir as primary key in folders index, this is already present)
      id: (h.id ?? h.dir) as any,
    }));

    return {
      data,
      total: res.estimatedTotalHits ?? data.length,
    };
  },
};

// Escape quotes for Meilisearch filter strings
function escapeMeiliString(s: string): string {
  return s.replaceAll(`"`, `\\"`);
}

const catfileDataProvider = {
  getList: async (params: Record<string, any>) => {
    const client = new Meilisearch({
      host: MEILI_URL,
      apiKey: MEILI_API_KEY,
    });

    const index = client.index(INDEX_NAME);

    const filter = params.filter ?? {};

    // ---- Pagination (react-admin style) ----
    const page = Number(params.pagination?.page ?? 1);
    const perPage = Number(params.pagination?.perPage ?? 25);

    // Backward-compat if you sometimes pass limit/offset directly
    const limit = Number(params.limit ?? perPage);
    const offset = Number(params.offset ?? (page - 1) * perPage);

    // ---- Sort ----
    const sortStringArray: string[] = [];
    if (params.sort?.field) {
      sortStringArray.push(
        `${params.sort.field}:${String(params.sort.order).toLowerCase()}`,
      );
    }

    // ---- Search phrase ----
    const phraseParts: string[] = [];
    const q = (filter.q ?? "").toString().trim();
    if (q) phraseParts.push(q);

    const searchPhrase = phraseParts.join(" ").trim();

    // ---- Helpers ----
    const esc = (s: any) => String(s).replaceAll('"', '\\"');

    // Build: field = "a" OR field = "b"
    const orEquals = (field: string, values: any[]) => {
      const clean = values
        .map((v) => (v == null ? "" : String(v).trim()))
        .filter((v) => v.length > 0);
      if (!clean.length) return "";
      if (clean.length === 1) return `${field} = "${esc(clean[0])}"`;
      return `(${clean.map((v) => `${field} = "${esc(v)}"`).join(" OR ")})`;
    };

    // ---- Structured filters (exact/range) ----
    const clauses: string[] = [];

    // Existing filters
    if (filter.volume) {
      clauses.push(`volume = "${esc(filter.volume)}"`);
    }

    if (filter.name) {
      clauses.push(`name STARTS WITH "${esc(filter.name)}"`);
    }
    if (filter.path) {
      clauses.push(`name STARTS WITH "${esc(filter.path)}"`);
    }

    if (filter.dir_prefix) {
      clauses.push(`path STARTS WITH "${esc(filter.dir_prefix)}"`);
    }

    if (filter.size_gte != null && filter.size_gte !== "") {
      clauses.push(`size >= ${Number(filter.size_gte)}`);
    }
    if (filter.size_lte != null && filter.size_lte !== "") {
      clauses.push(`size <= ${Number(filter.size_lte)}`);
    }

    if (filter.created_gte) {
      clauses.push(`created >= "${esc(filter.created_gte)}"`);
    }
    if (filter.created_lte) {
      clauses.push(`created <= "${esc(filter.created_lte)}"`);
    }

    // ---- NEW: facet filters from ExplorerPage ----
    // Expect arrays like { ext: ["jpg","png"], camera_make: ["Apple"] }
    const FACET_FIELDS = [
      "kind",
      "ext",
      "camera_make",
      "camera_model",
      "lens_model",
    ];

    for (const field of FACET_FIELDS) {
      const v = filter[field];
      if (Array.isArray(v)) {
        const c = orEquals(field, v);
        if (c) clauses.push(c);
      } else if (typeof v === "string" && v.trim() !== "") {
        // allow single value too
        clauses.push(`${field} = "${esc(v)}"`);
      }
    }

    const meiliFilter = clauses.length ? clauses.join(" AND ") : undefined;

    // ---- NEW: facet distribution support ----
    // ExplorerPage calls getList("catfile_facets", { meta: { facets: [...] } })
    const requestedFacets: string[] | undefined = Array.isArray(
      params.meta?.facets,
    )
      ? params.meta.facets
      : undefined;

    // If this resource is only for facets, or if meta.facets is present and caller only wants facets,
    // we can short-circuit hits by setting limit=0.
    const isFacetsOnly =
      params.resource === "catfile_facets" || params.meta?.facetsOnly === true;

    const results = await index.search(searchPhrase, {
      sort:
        !isFacetsOnly && sortStringArray.length ? sortStringArray : undefined,
      limit: isFacetsOnly ? 0 : limit,
      offset: isFacetsOnly ? 0 : offset,
      filter: meiliFilter,
      facets: requestedFacets, // <-- key bit
    });

    const total = results.estimatedTotalHits ?? results.hits.length;

    // Meili JS returns facetDistribution when facets are requested.
    // Depending on SDK version it may be `facetDistribution` or `facetDistribution` under different names.
    const facetDistribution =
      (results as any).facetDistribution ??
      (results as any).facetsDistribution ??
      undefined;

    return {
      data: isFacetsOnly ? [] : results.hits,
      pageInfo: isFacetsOnly
        ? { hasPreviousPage: false, hasNextPage: false }
        : {
            hasPreviousPage: offset > 0,
            hasNextPage: offset + limit < total,
          },
      meta: facetDistribution ? { facets: facetDistribution } : undefined,
      // total, // optional
    };
  },

  getOne: async (params: Record<string, unknown>) => {
    try {
      const client = new Meilisearch({
        host: MEILI_URL,
        apiKey: MEILI_API_KEY,
      });
      const index = client.index(INDEX_NAME);
      const record = await index.getDocument(params.id);
      return { data: record };
    } catch (e) {
      console.log(e);
      //setError(String(e));
    } finally {
      //setSavingId(null);
    }
  },
};

const defectsDataProvider = {
  getList: async (params: Record<string, unknown>) => {
    try {
      const target = `https://api.qase.io/v1/defect/${PROJECT_CODE}/`;
      let url = buildProxyUrl(target, {
        ...{ limit: String(100), offset: String(0) },
        ...params,
      });
      url = "http://localhost:8020" + url;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`GET cases failed: ${res.status}`);
      const data = await res.json();
      return {
        data: data.result.entities,
        pageInfo: { hasPreviousPage: false, hasNextPage: false },
      };
    } catch (e) {
      console.log(e);
      //setError(String(e));
    } finally {
      //setSavingId(null);
    }
  },
  getOne: async (params: Record<string, unknown>) => {
    try {
      const target = `https://api.qase.io/v1/defect/${PROJECT_CODE}/${params.id}`;
      let url = buildProxyUrl(target, {
        ...{ limit: String(100), offset: String(0) },
        ...params,
      });
      url = "http://localhost:8020" + url;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`GET cases failed: ${res.status}`);
      const data = await res.json();
      const result = data.result;
      return { data: result };
    } catch (e) {
      console.log(e);
      //setError(String(e));
    } finally {
      //setSavingId(null);
    }
  },
  delete: async (params: Record<string, unknown>) => {
    try {
      const target = buildProxyUrl(
        `https://api.qase.io/v1/defect/${PROJECT_CODE}/${params.id}`,
      );
      const res = await fetch("http://localhost:8020" + target, {
        method: "DELETE",
        headers: { "content-type": "application/json" },
      });
      if (!res.ok) throw new Error(`Delete case  failed: ${res.status}`);
      const data = await res.json();
      return { data: { id: data.result.id } };
    } catch (e) {
      console.log(String(e));
    }
  },
  update: async (params: DefectCreateParams) => {
    try {
      const target = `https://api.qase.io/v1/defect/${PROJECT_CODE}/${params.id}`;

      const raw_body = {
        title: params.data.title.trim(),
        actual_result: params.data.actual_result || "Not specified",
        status: params.data.status,
        severity: params.data.severity,
        // If your Qase requires more fields (e.g., severity, suite_id), add them here.
      };
      const body = JSON.stringify(raw_body);

      const res = await fetch("http://localhost:8020" + buildProxyUrl(target), {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body,
      });

      if (!res.ok) throw new Error(`Delete case  failed: ${res.status}`);

      return { data: raw_body };
    } catch (e) {
      console.log(String(e));
    }
  },
  deleteMany: async (params: {
    ids: number[];
  }): Promise<{ data: number[] | undefined }> => {
    try {
      const ids: number[] = params.ids;
      const results = [];
      for (const id of ids) {
        results.push(await defectsDataProvider.delete({ id }));
      }
      return { data: ids };
    } catch (e) {
      console.log(String(e));
      return { data: undefined };
    }
  },
  create: async (params: DefectCreateParams) => {
    try {
      const target = `https://api.qase.io/v1/defect/${PROJECT_CODE}/`;
      const raw_body = {
        title: params.data.title.trim(),
        actual_result: params.data.actual_result || "Not specified",
        status: 1,
        severity: 1,
        // If your Qase requires more fields (e.g., severity, suite_id), add them here.
      };
      const body = JSON.stringify(raw_body);

      const res = await fetch("http://localhost:8020" + buildProxyUrl(target), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body,
      });

      if (!res.ok) {
        const t = await res.text().catch(() => "");
        throw new Error(`POST failed: ${res.status} ${t}`);
      }
      const data = await res.json();
      const response: DefectRecord = {};
      response["id"] = data.result.id;
      response["title"] = raw_body.title;
      response["actual_result"] = raw_body.actual_result;
      return { data: response };
    } catch (e) {
      console.log(e);
    } finally {
      //setAddBusy(false);
    }
  },
};

const dataProviders = {
  defects: defectsDataProvider,
  catfile: catfileDataProvider,
  folders: foldersDataProvider,
  travellist_items: travelListItemProvider,
  travellist_categories: travelListCategoryProvider,
  travellist_tags: travelListTagProvider,
  travellist_listitems: travelListListItemProvider,
};

type Resource = keyof typeof dataProviders; // "defects" | "assets" | ...

export const dataProvider = {
  // get a list of records based on sort, filter, and pagination
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  getList: (resource: Resource, _params: never) => {
    const dataProvider = dataProviders[resource];
    return dataProvider.getList(_params);
  },
  updateMany: (resource: Resource, _params: never) => {
    const dataProvider = dataProviders[resource];
    return dataProvider.updateMany(_params);
  },
  // get a single record by id
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  getOne: (resource: Resource, _params: never) => {
    const dataProvider = dataProviders[resource];
    return dataProvider.getOne(_params);
  },
  // get the records referenced to another record, e.g. comments for a post
  getManyReference: (resource: never, params: never) => {
    return { resource, params };
  },
  // create a record
  create: (resource: Resource, _params: never) => {
    const dataProvider = dataProviders[resource];
    return dataProvider.create(_params);
  },
  // update a record based on a patch
  update: (resource: Resource, _params: never) => {
    const dataProvider = dataProviders[resource];
    return dataProvider.update(_params);
  },
  // delete a record by id
  delete: (resource: Resource, _params: never) => {
    const dataProvider = dataProviders[resource];
    return dataProvider.delete(_params);
  },
  // delete a list of records based on an array of ids
  deleteMany: (resource: Resource, _params: never) => {
    const dataProvider = dataProviders[resource];
    return dataProvider.deleteMany(_params);
  },
};
