// in src/users.tsx
import {
  List,
  SimpleList,
  Edit,
  Create,
  DataTable,
  EmailField,
  Show,
  SimpleShowLayout,
  useShowContext,
  TextField,
  TextInput,
  FunctionField,
  SimpleForm,
} from "react-admin";
import Tooltip from "@mui/material/Tooltip";
import { SelectInput, DateInput, NumberInput } from "react-admin";
import { useMediaQuery, Theme } from "@mui/material";
import { useRecordContext } from "react-admin";
import { Dialog, DialogContent } from "@mui/material";
import { useState } from "react";
import * as React from "react";
import { Labeled } from "react-admin";
import Accordion from "@mui/material/Accordion";
import AccordionSummary from "@mui/material/AccordionSummary";
import AccordionDetails from "@mui/material/AccordionDetails";
import Typography from "@mui/material/Typography";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

const PrettyKey = ({ k }) => (
  <span style={{ fontWeight: 600 }}>{k.replaceAll("_", " ")}</span>
);

const humanSize = (bytes) => {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;

  const units = ["K", "M", "G", "T"];
  let i = -1;
  let size = bytes;

  do {
    size /= 1024;
    i++;
  } while (size >= 1024 && i < units.length - 1);

  return `${size.toFixed(size < 10 ? 1 : 0)} ${units[i]}`;
};
// @ts-expect-error/Iknow
const ThumbnailWithPreview = ({ source }) => {
  const [open, setOpen] = useState(false);
  const record = useRecordContext();
  const value = record?.[source];
  const volume = record?.["volume"];
  const path = record?.["path"];
  const filename = record?.["name"];

  const handleOpen = (e) => {
    e.preventDefault();
    e.stopPropagation(); // <-- THIS is the key
    setOpen(true);
  };

  const handleClose = (e) => {
    // when clicking close/backdrop, also stop row click if needed
    if (e?.stopPropagation) e.stopPropagation();
    setOpen(false);
  };

  return (
    <>
      <img
        src={value}
        alt={record?.name || ""}
        width={56}
        height={56}
        style={{
          objectFit: "cover",
          borderRadius: 6,
          cursor: "pointer",
        }}
        onClick={handleOpen}
      />

      <Dialog
        open={open}
        onClose={(e) => {
          e?.preventDefault?.();
          e?.stopPropagation?.();
          setOpen(false);
        }}
        slotProps={{
          paper: {
            onClick: (e) => {
              e.preventDefault();
              e.stopPropagation(); // stops rowClick behind dialog
            },
          },
          backdrop: {
            onClick: handleClose, // optional; onClose also handles backdrop
          },
        }}
        maxWidth="lg"
      >
        <DialogContent sx={{ p: 1 }}>
          <img
            src={`http://localhost:5000/images?volume=${volume}&path=${path}&filename=${filename}`}
            alt={record?.name || ""}
            style={{
              maxWidth: "100%",
              maxHeight: "90vh",
              display: "block",
              margin: "0 auto",
            }}
          />
        </DialogContent>
      </Dialog>
    </>
  );
};

const Base64ThumbField = ({ source, width = 64, height = 64, titleSource }) => {
  const record = useRecordContext();
  const value = record?.[source];
  if (!value) return null;

  const title = titleSource ? record?.[titleSource] : "";

  return (
    <img
      src={value}
      alt={title || ""}
      title={title || ""}
      width={width}
      height={height}
      style={{
        objectFit: "cover",
        borderRadius: 6,
        display: "block",
      }}
      loading="lazy"
    />
  );
};

const volumeChoices = [
  { id: "SYN_PHOTO", name: "SYN_PHOTO" },
  { id: "SYN_DATA", name: "SYN_DATA" },
  // or load dynamically (see note below)
];

const catFileFilters = [
  // global search
  <TextInput key="q" source="q" label="Search" alwaysOn resettable />,

  // field-specific text search
  <TextInput key="name" source="name" label="Name contains" resettable />,
  <TextInput key="path" source="path" label="Path contains" resettable />,

  // dropdown
  <SelectInput
    key="volume"
    source="volume"
    label="Volume"
    choices={volumeChoices}
    resettable
  />,

  // date range (two inputs)
  <DateInput
    key="created_gte"
    source="created_gte"
    label="Created after"
    resettable
  />,
  <DateInput
    key="created_lte"
    source="created_lte"
    label="Created before"
    resettable
  />,

  // numeric range
  <NumberInput
    key="size_gte"
    source="size_gte"
    label="Min size (bytes)"
    resettable
  />,
  <NumberInput
    key="size_lte"
    source="size_lte"
    label="Max size (bytes)"
    resettable
  />,
];

export const CatFileList = () => {
  const isSmall = useMediaQuery<Theme>((theme) => theme.breakpoints.down("sm"));
  return (
    <List filters={catFileFilters}>
      {isSmall ? (
        <SimpleList
          primaryText={(record) => record.name}
          secondaryText={(record) => record.username}
          tertiaryText={(record) => record.email}
        />
      ) : (
        <DataTable>
          <DataTable.Col
            label="Preview"
            source="thumbnail"
            render={(value, record) => (
              <ThumbnailWithPreview
                source="thumbnail"
                titleSource="name"
                width={56}
                height={56}
              />
            )}
          />
          <DataTable.Col source="created" sortable />
          <DataTable.Col source="volume" />
          <DataTable.Col source="path" />
          <DataTable.Col source="name" />
          <DataTable.Col
            label="Size"
            source="size"
            render={(value) =>
              value != null ? (
                <Tooltip title={`${value.size.toLocaleString()} bytes`} arrow>
                  <span>{humanSize(value.size)}</span>
                </Tooltip>
              ) : null
            }
          />
        </DataTable>
      )}
    </List>
  );
};

const CatFileShowContent = () => {
  const { record, isLoading } = useShowContext();
  if (isLoading || !record) return null;

  const { name, path, volume, size } = record; // custom code here

  return (
    <SimpleShowLayout>
      <TextField source="volume" />
      <TextField source="path" />
      <TextField source="name" />
      <FunctionField
        label="Size"
        render={(record) =>
          record?.size != null ? (
            <Tooltip title={`${record.size.toLocaleString()} bytes`} arrow>
              <span>{humanSize(record.size)}</span>
            </Tooltip>
          ) : null
        }
      />
      <ThumbnailWithPreview
        source="thumbnail"
        titleSource="name"
        width={56}
        height={56}
      />
      {/* Optional fields */}
      {record.exif && <ExifSection exif={record.exif} />}
      {record.info && <VideoInfoSection info={record.info} />}
    </SimpleShowLayout>
  );
};
export const ExifSection = ({ exif }) => {
  if (!exif) return null;

  // Split out raw
  const { exif_data_raw, ...basic } = exif;

  // Show only meaningful basic fields
  const basicEntries = Object.entries(basic).filter(
    ([, v]) => v !== null && v !== undefined && v !== "",
  );

  return (
    <div style={{ marginTop: 16 }}>
      <Typography variant="h6" sx={{ mb: 1 }}>
        EXIF
      </Typography>

      {/* Basic fields */}
      {basicEntries.length ? (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "160px 1fr",
            gap: "8px 16px",
          }}
        >
          {basicEntries.map(([k, v]) => (
            <React.Fragment key={k}>
              <PrettyKey k={k} />
              <span>
                {typeof v === "object" ? JSON.stringify(v) : String(v)}
              </span>
            </React.Fragment>
          ))}
        </div>
      ) : (
        <Typography variant="body2" color="text.secondary">
          No parsed EXIF fields.
        </Typography>
      )}

      {/* Raw data collapsible */}
      {exif_data_raw ? (
        <div style={{ marginTop: 12 }}>
          <Accordion
            defaultExpanded={false}
            onClick={(e) => e.stopPropagation()} // important inside react-admin row contexts
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography variant="subtitle1">
                Raw EXIF (exif_data_raw)
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              <pre
                style={{
                  margin: 0,
                  padding: 12,
                  borderRadius: 8,
                  overflow: "auto",
                  maxHeight: 360,
                  background: "rgba(0,0,0,0.04)",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  fontFamily:
                    'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
                  fontSize: 12,
                  lineHeight: 1.4,
                }}
                onClick={(e) => e.stopPropagation()} // prevents clicks bubbling to parent
              >
                {typeof exif_data_raw === "string"
                  ? exif_data_raw
                  : JSON.stringify(exif_data_raw, null, 2)}
              </pre>
            </AccordionDetails>
          </Accordion>
        </div>
      ) : null}
    </div>
  );
};

const VideoInfoSection = ({ info }) => (
  <div style={{ marginTop: 16 }}>
    <h3>Video Info</h3>
    <pre style={{ whiteSpace: "pre-wrap" }}>
      {JSON.stringify(info, null, 2)}
    </pre>
  </div>
);

export const CatFileShow = () => (
  <Show>
    <CatFileShowContent />
  </Show>
);
