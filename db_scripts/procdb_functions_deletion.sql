DROP TYPE IF EXISTS RunSubrunList CASCADE;
DROP FUNCTION IF EXISTS MakeProjTable(TEXT);
DROP FUNCTION IF EXISTS InsertIntoProjTable(TEXT,INT,INT);
DROP FUNCTION IF EXISTS IncreaseProjSequence(TEXT,INT,INT,SMALLINT,SMALLINT);
DROP FUNCTION IF EXISTS UpdateProjStatus(TEXT,INT,INT,SMALLINT,SMALLINT);
DROP FUNCTION IF EXISTS UpdateProjStatus(TEXT,INT,INT,SMALLINT,SMALLINT,TEXT);
DROP FUNCTION IF EXISTS GetProjectData( project_name TEXT,
     	      	 			run    INT,
					subrun INT,
					seq    SMALLINT);
DROP FUNCTION IF EXISTS GetRuns(project_name TEXT,status INT);
DROP FUNCTION IF EXISTS GetRuns(TEXT[],SMALLINT[]);
