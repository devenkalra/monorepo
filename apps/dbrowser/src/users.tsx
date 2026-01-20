// in src/users.tsx
import { List, SimpleList, DataTable, EmailField } from "react-admin";
import { useMediaQuery, Theme } from "@mui/material";

export const UserList = () => {
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
          <DataTable.Col source="id"/>
          <DataTable.Col source="name"/>
          <DataTable.Col source="username"/>
          <DataTable.Col source="email">
            <EmailField source="email"/>
          </DataTable.Col>
          <DataTable.Col source="address.street"/>
          <DataTable.Col source="phone"/>
          <DataTable.Col source="website"/>
          <DataTable.Col source="company.name"/>
        </DataTable>
      )}
    </List>
  );
};