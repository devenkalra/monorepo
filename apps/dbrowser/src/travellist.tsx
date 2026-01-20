// in src/users.tsx
import {
  List,
  SimpleList,
  Edit,
  Create,
  DataTable,
  ReferenceInput,
  ReferenceArrayInput,
  SelectArrayInput,
  EmailField,
  BooleanField,
  SelectInput,
  Show,
  SimpleShowLayout,
  TextField,
  TextInput,
  SimpleForm,
} from "react-admin";
import DoneIcon from "@mui/icons-material/Done";
import PriorityHighIcon from "@mui/icons-material/PriorityHigh";
import {
  useUpdateMany,
  useListContext,
  useNotify,
  useUnselectAll,
} from "react-admin";
import { useMediaQuery, Theme } from "@mui/material";
import { Chip, Button } from "@mui/material";

const MarkAsNeededButton = () => {
  const { selectedIds } = useListContext();
  const notify = useNotify();
  const unselectAll = useUnselectAll();

  const [updateMany, { isLoading }] = useUpdateMany(
    "travellist_listitems", // Your resource name
    { ids: selectedIds, data: { need: true, status: "needed" } },
    {
      onSuccess: () => {
        notify("Items marked as needed");
        unselectAll();
      },
      mutationMode: "pessimistic",
    },
  );

  return (
    <Button
      label="Mark Needed"
      onClick={() => updateMany()}
      disabled={isLoading}
      startIcon={<PriorityHighIcon />}
    >
      Mark Needed
    </Button>
  );
};

const MarkAsDoneButton = () => {
  const { selectedIds } = useListContext();
  const [updateMany] = useUpdateMany(
    "travellist_listitems",
    { ids: selectedIds, data: { done: true, status: "needed" } },
    { mutationMode: "pessimistic" },
  );

  return (
    <Button onClick={() => updateMany()} startIcon={<DoneIcon />}>
      Mark Done
    </Button>
  );
};
import { BulkDeleteButton } from "react-admin";

const MyBulkActionButtons = () => (
  <>
    <MarkAsNeededButton />
    <MarkAsDoneButton />
    {/* You can still keep the standard delete button if you want */}
    <BulkDeleteButton />
  </>
);
export const TravelItemList = () => {
  const isSmall = useMediaQuery<Theme>((theme) => theme.breakpoints.down("sm"));
  return (
    <List>
      {isSmall ? (
        <SimpleList
          primaryText={(record) => record.name}
          secondaryText={(record) => record.username}
          tertiaryText={(record) => record.email}
        />
      ) : (
        <DataTable>
          <DataTable.Col source="name" />
          <DataTable.Col source="category.name" />
          <DataTable.Col
            label="Tags"
            source="tags"
            render={(record) => (
              <div style={{ display: "flex", gap: "4px" }}>
                {record.tags?.map((tag: any) => (
                  <Chip key={tag.id} label={tag.name} size="small" />
                ))}
              </div>
            )}
          />
        </DataTable>
      )}
    </List>
  );
};

export const TravelListItemList = () => {
  const isSmall = useMediaQuery<Theme>((theme) => theme.breakpoints.down("sm"));
  return (
    <List>
      {isSmall ? (
        <SimpleList
          primaryText={(record) => record.item.name}
          secondaryText={(record) => record.username}
          tertiaryText={(record) => record.email}
        />
      ) : (
        <DataTable bulkActionButtons={<MyBulkActionButtons />}>
          <DataTable.Col label="Name" source="item.name" />
          <DataTable.Col label="Category" source="item.category.name" />
          <DataTable.Col source="need" label="Needed">
            <BooleanField source="need" />
          </DataTable.Col>
          <DataTable.Col label="Done" source="done" />
          <DataTable.Col
            label="Tags"
            source="tags"
            render={(record) => (
              <div style={{ display: "flex", gap: "4px" }}>
                {record.item.tags?.map((tag: any) => (
                  <Chip key={tag.id} label={tag.name} size="small" />
                ))}
              </div>
            )}
          />
        </DataTable>
      )}
    </List>
  );
};

export const DefectShow = () => (
  <Show>
    <SimpleShowLayout>
      <TextField source="id" />
      <TextField source="title" />
      <TextField source="actual_result" />
      <TextField source="severity" />
    </SimpleShowLayout>
  </Show>
);

export const TravelItemEdit = () => (
  <Edit>
    <SimpleForm>
      <TextInput source="name" />
    </SimpleForm>
  </Edit>
);

export const TravelItemCreate = () => (
  <Create>
    <SimpleForm>
      <TextInput source="name" />
      <TextInput source="description" multiline />

      {/* Single Select Dropdown */}
      <ReferenceInput source="category" reference="travellist_categories">
        <SelectInput optionText="name" />
      </ReferenceInput>

      {/* Multi-Select for Tags */}
      <ReferenceArrayInput source="tags" reference="travellist_tags">
        <SelectArrayInput optionText="name" />
      </ReferenceArrayInput>
    </SimpleForm>
  </Create>
);

export const TravelListItemCreate = () => (
  <Create>
    <SimpleForm>
      <TextInput source="name" />
      <TextInput source="description" multiline />

      {/* Single Select Dropdown */}
      <ReferenceInput source="category" reference="travellist_categories">
        <SelectInput optionText="name" />
      </ReferenceInput>

      {/* Multi-Select for Tags */}
      <ReferenceArrayInput source="tags" reference="travellist_tags">
        <SelectArrayInput optionText="name" />
      </ReferenceArrayInput>
    </SimpleForm>
  </Create>
);

export const TravelItemCreateX = () => (
  <Create>
    <SimpleForm>
      {/* Usually, IDs are auto-generated by the backend; remove this if yours is! */}
      <TextInput source="id" />
      <TextInput source="name" />

      {/* Dropdown for Categories */}
      <ReferenceInput source="category" reference="travellist_categories">
        <SelectInput optionText="name" />
      </ReferenceInput>
    </SimpleForm>
  </Create>
);
