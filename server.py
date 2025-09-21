# Licensed under Functional Source License (FSL) FSL-1.1-MIT
# See README.md, LICENSE in the project root for license information.

import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Annotated, Optional, Literal
from pathlib import Path

from pydantic import Field
from markdownify import markdownify as md

from fastmcp import FastMCP, Context
from mcp.types import ImageContent

import saspy

class SASSessionManager:
    """Wrapper around saspy.SASsession providing restart/end methods."""
    def __init__(self, **kwargs: Any):
        """
        Initialize SAS session with optional kwargs.
        If 'SAS_AUTOEXEC' or 'SAS_CFGNAME' are in environment variables,
        they will be used as SAS session parameters.
        """
        self._kwargs = kwargs
        if 'autoexec' not in kwargs and 'SAS_AUTOEXEC' in os.environ:
            self._kwargs['autoexec'] = os.environ['SAS_AUTOEXEC']
        if 'cfgname' not in kwargs and 'SAS_CFGNAME' in os.environ:
            self._kwargs['cfgname'] = os.environ['SAS_CFGNAME']

        self.session: Optional[saspy.SASsession] = None
        self._create()

    def _create(self) -> None:
        self.session = saspy.SASsession(**self._kwargs)

    def restart(self) -> str:
        if self.session is not None:
            self.session.endsas()
        self._create()
        return "SAS session restarted."

    def end(self) -> str:
        if self.session is not None:
            self.session.endsas()
            self.session = None
        return "SAS session ended."

@dataclass
class AppContext:
    sas: SASSessionManager

@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage app startup and shutdown lifecycle with SASSessionManager wrapper."""
    sas = SASSessionManager()
    try:
        yield AppContext(sas=sas)
    finally:
        sas.end()

def _get_content(ll: dict, short: bool = True, max_len: int = 4000) -> str|list[ImageContent]:
    """
    Determines if the log or lst should be returned as the
    results for the cell based on parsing the log
    looking for errors and the presence of lst output.

    Part of the logic is based on sas_kernel:
    https://github.com/sassoftware/sas_kernel/blob/main/sas_kernel/kernel.py

    Parameters
    ----------
    ll : dict
        Dictionary with 'LOG' and 'LST' keys from saspy submit method.
    short : bool, optional
        If True, return a truncated output or log if length exceeds max_len,
        or a simple message when there are no errors and no LST output.
        If False, return the full output or log in such cases. Default is True.
    max_len : int, optional
        Maximum length of LST output to return. If the LST exceeds this length,
        it will be truncated. Default is 4000 characters.

    Returns
    -------
    str | list[ImageContent]
        The processed output based on the input content.
        - If output contains embedded images, returns a list of ImageContent objects.
        - If output format is HTML, returns it as markdown.
        - If there are errors in the log, sas_kernel style output is returned.
        
    """
    
    log = ll["LOG"]
    if bool(re.search(r'<!DOCTYPE html>', ll["LST"], re.IGNORECASE)):
        lst = md(ll["LST"])
    else:
        lst = ll["LST"]

    if len(lst) > max_len and short:
        lst = lst[:max_len-30] + "\n\n[Output is truncated.]"

    # Check Error
    lines = re.split(r'[\n]\s*', log)
    error_count = 0
    msg_list = []
    error_line_list = []
    for index, line in enumerate(lines):
        if line.startswith('ERROR'):
            error_count += 1
            msg_list.append(line)
            error_line_list.append(index)

    img_tags = re.findall(r'<img[^>]*>', ll["LST"])
    # return encoded image
    if img_tags:
        images = []
        for img_tag in img_tags:
            m = re.search(r'alt="([^"]*)"\s*src="data:([^;]+);base64,([^"]+)"', img_tag)
            alt_txt =  m.group(1)
            mime_type = m.group(2)
            base64_data = m.group(3)
            images.append(ImageContent(
                type="image",
                data=base64_data,
                mimeType=mime_type,
                annotations={
                    "title": alt_txt
                }
            ))
        return images

    # no error and LST output
    if error_count == 0 and len(lst) > 0:
        return lst
    elif error_count > 0 and len(lst) > 0 and not img_tags:  # errors and LST
        # filter log to lines around first error
        # by default get 5 lines on each side of the first Error message.
        # to change that modify the values in {} below
        regex_around_error = r"(.*)(.*\n){6}^ERROR(.*\n){6}"
        # Extract the first match +/- 5 lines
        e_log = re.search(regex_around_error, log, re.MULTILINE).group()
        assert error_count == len(
            error_line_list), "Error count and count of line number don't match"
        return e_log + lst
    # for everything else return the log
    if not short:
        return log
    else:
        return "Code executed with No Errors."

mcp = FastMCP(name="basic-mcp-sas-server",
              instructions= "MCP server that executes SAS code, provides information related to SAS with saspy.", 
              lifespan=app_lifespan
              )

@mcp.tool(description="Submit SAS code for execution. Use this if no other tool is appropriate.",
          tags={"sas"}
          )
def submit(ctx: Context, code: Annotated[str, "SAS code to submit. Only SAS code is allowed."], 
           results: Annotated[Literal["HTML", "TEXT"], Field(description="Specify `TEXT` only if there is a problem with the default output or if explicitly instructed.", default="HTML")],
           short: Annotated[bool, Field(description="KEEP this set to True. Only if explicitly instructed to output without omitting, set to False.", default=True)]
           ) -> str | ImageContent:
    """Submit SAS code for execution.
    
    Note: While this tool is convenient, it executes code as-is, which means problematic or unsafe code could be run. 
          It is recommended to configure more specific tools and consider disabling this tool for improved safety.
    """
    sas = ctx.request_context.lifespan_context.sas.session
    ll = sas.submit(code, results=results)
    return _get_content(ll, short)

@mcp.tool(tags={"sas"})
def restart(ctx: Context) -> str:
    """Restart SAS session. Only execute if explicitly instructed."""
    sas_sm = ctx.request_context.lifespan_context.sas
    return sas_sm.restart()

@mcp.tool(tags={"sas", "meta"})
def assigned_librefs(ctx: Context) -> list:
    """List SAS assigned libraries."""
    sas = ctx.request_context.lifespan_context.sas.session
    result = sas.assigned_librefs() 
    return result

@mcp.tool(tags={"sas", "meta"})
def list_tables(ctx: Context, libref: Annotated[str, "SAS libname."]) -> list:
    """List SAS tables in a library."""
    sas = ctx.request_context.lifespan_context.sas.session
    result = sas.list_tables(libref=libref)
    return result

@mcp.tool(tags={"sas", "meata"})
def columnInfo_t(ctx: Context, table: Annotated[str, Field(description="SAS table name.")],
               libref: Annotated[str, Field(description="SAS libname.", default="WORK")]) -> dict:
    """Get column information of a SAS dataset."""
    sas = ctx.request_context.lifespan_context.sas.session
    ds = sas.sasdata(table, libref, results="TEXT")
    return ds.columnInfo()

@mcp.tool(tags={"sas", "data"})
def head(ctx: Context,  table: Annotated[str, Field(description="SAS table name.")], 
         libref: Annotated[str, Field(description="SAS libname.", default="WORK")],
         obs: Annotated[int, Field(description="Number of rows to return.", ge=0, default=5)] ) -> str:
    """Get the first few rows of a SAS dataset."""
    sas = ctx.request_context.lifespan_context.sas.session
    ds = sas.sasdata(table, libref, results="TEXT")
    return ds.head(obs=obs)

@mcp.tool(tags={"sas", "data"})
def print(ctx: Context,  table: Annotated[str, Field(description="SAS table name.")], 
         libref: Annotated[str, Field(description="SAS libname.", default="WORK")],
         var: Annotated[str, Field(description="Variable to print.", default="_ALL_")]
         ) -> str:
    """Print all SAS dataset obs with variable labels."""
    sas = ctx.request_context.lifespan_context.sas.session
    ll = sas.submit(f"proc print data={libref}.{table} label ; var {var}; run;")
    return _get_content(ll, short=False)

@mcp.resource("file://{path}",
              annotations={ "readOnlyHint": True,}
              ,tags={"sas", "file"}
              )
def cat(ctx: Context, path: Annotated[Path, "File path to read."]) -> str:
    """Get file contents. Like `cat` in Unix."""
    sas = ctx.request_context.lifespan_context.sas.session
    result = sas.cat(path)
    return result

@mcp.resource("sasdata://{libref}/{table}/columnInfo",
              annotations={"readOnlyHint": True,},
              tags={"sas", "meta"}
              )
def columnInfo_r(ctx: Context, table: Annotated[str, Field(description="SAS table name.")],
               libref: Annotated[str, Field(description="SAS libname.", default="WORK")]) -> dict:
    """Get column information of a SAS dataset."""
    sas = ctx.request_context.lifespan_context.sas.session
    ds = sas.sasdata(table, libref, results="TEXT")
    return ds.columnInfo()

if __name__ == "__main__":
    mcp.run(transport="stdio")
    # mcp.run(transport="streamable-http", host="127.0.0.1", port=8000, path="/mcp")
