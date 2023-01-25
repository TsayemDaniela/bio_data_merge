$('#interactor_query').submit(function (e) {
    let dbsToCheck = [];
    e.preventDefault();
    console.log(e)
    const { target: { elements: { BioGRID, IntAct, STRING, interactorName: { value: interactorName } } } } = e;
    [BioGRID, IntAct, STRING].forEach((db) => {
        if (db.checked) {
            dbsToCheck.push(db.id)
        }
    })
    let body = { interactorName, dbsToCheck: dbsToCheck }
    // send a post request to web server with dbsToCheck and interactor_name as part of the body
    const url = '/interactor/search'
    const cb = (data) => {
        // redirect to result page
        window.location = "/interactor/search/results"
    }
    $.post(url, body, cb);
})