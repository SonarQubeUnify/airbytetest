import React, { useCallback } from "react";
import { useNavigate } from "react-router-dom";

import { ConnectionTable } from "components/EntityTable";
import useSyncActions from "components/EntityTable/hooks";
import { ITableDataItem } from "components/EntityTable/types";
import { getConnectionTableData } from "components/EntityTable/utils";

import { RoutePaths } from "pages/routePaths";

import { WebBackendConnectionListItem } from "../../../../../core/request/AirbyteClient";

interface IProps {
  connections: WebBackendConnectionListItem[];
}

const DestinationConnectionTable: React.FC<IProps> = ({ connections }) => {
  const navigate = useNavigate();
  const { syncManualConnection } = useSyncActions();

  const data = getConnectionTableData(connections, "destination");

  const onSync = useCallback(
    async (connectionId: string) => {
      const connection = connections.find((item) => item.connectionId === connectionId);
      if (connection) {
        await syncManualConnection(connection);
      }
    },
    [connections, syncManualConnection]
  );

  const clickRow = (source: ITableDataItem) => navigate(`../../../${RoutePaths.Connections}/${source.connectionId}`);

  return <ConnectionTable data={data} onClickRow={clickRow} entity="destination" onSync={onSync} />;
};

export default DestinationConnectionTable;
