import { Admin, Resource, CustomRoutes } from "react-admin";
import { UserList } from "./users";
import { DefectList, DefectShow, DefectEdit, DefectCreate } from "./defects";
import {
  TravelListItemList,
  TravelItemList,
  TravelItemEdit,
  TravelItemCreate,
} from "./travellist.tsx";
import { CatFileList, CatFileShow } from "./catfiles";
import { ExplorerPage } from "./ExplorerPage";
import { Layout } from "./Layout";
import { dataProvider } from "./dataProvider";
import { authProvider } from "./authProvider";
import { Route } from "react-router-dom";
export const App = () => (
  <Admin
    layout={Layout}
    dataProvider={dataProvider}
    authProvider={authProvider}
  >
    <CustomRoutes>
      <Route path="/explorer" element={<ExplorerPage />} />
    </CustomRoutes>
    <Resource
      name="defects"
      list={DefectList}
      show={DefectShow}
      edit={DefectEdit}
      create={DefectCreate}
    />
    <Resource
      name="travellist_items"
      list={TravelItemList}
      show={DefectShow}
      edit={TravelItemEdit}
      create={TravelItemCreate}
    />
    <Resource
      name="travellist_listitems"
      list={TravelListItemList}
      show={DefectShow}
      edit={TravelItemEdit}
      create={TravelItemCreate}
    />
    <Resource
      name="travellist_categories"
      list={TravelItemList}
      show={DefectShow}
      edit={TravelItemEdit}
      create={TravelItemCreate}
    />
    <Resource
      name="travellist_tags"
      list={TravelItemList}
      show={DefectShow}
      edit={TravelItemEdit}
      create={TravelItemCreate}
    />
    <Resource
      name="catfile"
      list={CatFileList}
      show={CatFileShow}
      //edit={DefectEdit}
      //create={DefectCreate}
    />
    <Resource name="users" list={UserList} />
  </Admin>
);
