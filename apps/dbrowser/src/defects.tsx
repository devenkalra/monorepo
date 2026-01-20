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
  TextField,
  TextInput,
  SimpleForm,
} from "react-admin";
import { useMediaQuery, Theme } from "@mui/material";

export const DefectList = () => {
  const isSmall = useMediaQuery<Theme> ((theme) => theme.breakpoints.down ("sm"));
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
          <DataTable.Col source="title" />
          <DataTable.Col source="actual_result" />
          <DataTable.Col source="email">
            <EmailField source="email" />
          </DataTable.Col>
          <DataTable.Col source="severity" />
        </DataTable>
      )}
    </List>
  );
};

export const DefectShow = () => (
  <Show>
    <SimpleShowLayout>
      <TextField source="id"/>
      <TextField source="title"/>
      <TextField source="actual_result"/>
      <TextField source="severity"/>
    </SimpleShowLayout>
  </Show>
);

export const DefectEdit = () => (
  <Edit>
    <SimpleForm>
      <TextInput source="id"/>
      <TextInput source="title"/>
      <TextInput source="actual_result"/>
    </SimpleForm>
  </Edit>
);

export const DefectCreate = () => (
  <Create>
    <SimpleForm>
      <TextInput source="id"/>
      <TextInput source="title"/>
      <TextInput source="actual_result"/>
    </SimpleForm>
  </Create>
);
